"""로또 LSTM 두뇌 — app.lotto 독립 패키지.

역할: 과거 당첨(멀티핫 45) 시퀀스로 다음 회차 번호 출현 경향(PMF)을 추정한다.
인터페이스: get_lstm_prob_vector(draws) -> dict[int, float] (키 1~45, 합≈1.0)
의존성: PyTorch(선택). torch 미설치 시 균등 PMF로 동작.
작성일: 2026-04-20
"""
from __future__ import annotations

import logging
import os
import pickle
from pathlib import Path
from typing import Any

# ── torch 미설치 시: 모듈은 로드되고 공개 API는 균등 PMF만 반환
try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    _TORCH_OK = True
except ImportError:  # pragma: no cover
    _TORCH_OK = False
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    DataLoader = None  # type: ignore[assignment]
    TensorDataset = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ── 상수
SEQ_LEN = 50
HIDDEN = 128
NUM_LAYERS = 2
DROPOUT = 0.2
EPOCHS = 30
BATCH = 32
RETRAIN_INTERVAL = 50
EPOCHS_EPHEMERAL = 5  # 과거 시점 임시학습 — 디스크 ckpt를 짧게 덮지 않음
# 프로젝트 루트: .../My_Library (app/lotto/ 기준 3단계 상위)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CKPT_PATH = _PROJECT_ROOT / "models" / "lstm_lotto.pt"
CKPT_FORMULA = "T-GATE-ML6"  # softmax ckpt와 호환 금지
_NUM_KEYS = list(range(1, 46))

_MODEL: Any = None
_LAST_TRAINED_LEN: int = 0
_DEVICE_USED: str = "cpu"
_MODEL_EPHEMERAL: bool = False

_NUM_FIELD_KEYS: tuple[str, ...] = ("num1", "num2", "num3", "num4", "num5", "num6")


def ckpt_usable_for_horizon(n_draws: int, last_trained_on: int) -> bool:
    """디스크/메모리 가중치는 학습 길이가 현재 입력 길이를 넘으면 사용 금지 (lookahead)."""
    return int(last_trained_on) > 0 and int(last_trained_on) <= int(n_draws)


def should_persist_checkpoint(n_draws: int, disk_last_trained_on: int | None) -> bool:
    """공식 체크포인트는 expanding window만. 과거 시점 임시학습은 저장하지 않음."""
    if disk_last_trained_on is None or int(disk_last_trained_on) <= 0:
        return True
    return int(n_draws) >= int(disk_last_trained_on)


def _uniform_pmf() -> dict[int, float]:
    p = 1.0 / 45.0
    return {i: p for i in _NUM_KEYS}


def _assert_pmf(result: dict[int, float]) -> None:
    assert len(result) == 45, "pmf len"
    assert set(result.keys()) == set(range(1, 46)), "pmf keys"
    assert abs(sum(result.values()) - 1.0) < 1e-6, "pmf sum"
    assert all(v >= 0 for v in result.values()), "pmf nonneg"


def _renorm(d: dict[int, float]) -> dict[int, float]:
    s = float(sum(d.values()))
    if s <= 0:
        return _uniform_pmf()
    return {k: float(v) / s for k, v in d.items()}


def _multihot_from_draw(d: dict) -> list[float]:
    v = [0.0] * 45
    for key in _NUM_FIELD_KEYS:
        n = int(d[key])
        if 1 <= n <= 45:
            v[n - 1] = 1.0
    return v


def _sort_by_draw_no(draws: list[dict]) -> list[dict]:
    return sorted(draws, key=lambda x: int(x.get("draw_no", 0)))


def _softmax_to_dict(soft: Any) -> dict[int, float]:
    """로짓 또는 확률 텐서를 1~45 PMF로. T-GATE-ML6는 시그모이드 후 정규화."""
    if hasattr(soft, "detach"):
        x = soft.detach().cpu().flatten()
        try:
            import torch as _T

            x = _T.sigmoid(x)
        except Exception:  # noqa: BLE001
            pass
    else:
        x = soft
    out: dict[int, float] = {}
    for i in range(45):
        out[i + 1] = float(x[i])
    return _renorm(out)


if _TORCH_OK:

    def _build_xy_tensors(
        draws: list[dict], device: Any
    ) -> tuple[Any, Any, int]:
        """(N, SEQ_LEN, 45), (N, 45) float, 샘플 수 n."""
        n = len(draws) - SEQ_LEN
        if n <= 0:
            raise ValueError("학습쌍 0")
        xs: list[list[list[float]]] = []
        ys: list[list[float]] = []
        for k in range(n):
            block = draws[k : k + SEQ_LEN + 1]
            seq = [_multihot_from_draw(block[j]) for j in range(SEQ_LEN)]
            target = _multihot_from_draw(block[SEQ_LEN])
            xs.append(seq)
            ys.append(target)
        x_t = torch.tensor(xs, dtype=torch.float32, device=device)  # type: ignore[union-attr]
        y_t = torch.tensor(ys, dtype=torch.float32, device=device)  # type: ignore[union-attr]
        return x_t, y_t, n

    class LottoLSTM(nn.Module):
        """(batch, T, 45) → (batch, 45) logits. 6/45 다중라벨 — softmax 금지."""

        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(  # type: ignore[union-attr]
                45, HIDDEN, num_layers=NUM_LAYERS, batch_first=True, dropout=DROPOUT
            )
            self.lin = nn.Linear(HIDDEN, 45)  # type: ignore[union-attr]

        def forward(self, x: Any) -> Any:
            out, _ = self.lstm(x)
            last = out[:, -1, :]
            return self.lin(last)

    def _is_oom(e: BaseException) -> bool:
        return isinstance(e, RuntimeError) and "out of memory" in str(e).lower()

    def _place_model(m: "LottoLSTM", prefer_cuda: bool) -> tuple["LottoLSTM", str]:
        if prefer_cuda and torch.cuda.is_available():  # type: ignore[union-attr]
            try:
                return m.to(torch.device("cuda")), "cuda"  # type: ignore[union-attr]
            except RuntimeError:
                return m.to(torch.device("cpu")), "cpu"  # type: ignore[union-attr]
        return m.to(torch.device("cpu")), "cpu"  # type: ignore[union-attr]

    def _train_on_device(
        model: "LottoLSTM", draws: list[dict], device: Any, epochs: int
    ) -> None:
        model = model.to(device)
        x_t, y_t, n_samples = _build_xy_tensors(draws, device)
        bsz = min(BATCH, max(1, n_samples))
        dataset = TensorDataset(x_t, y_t)  # type: ignore[operator]
        loader = DataLoader(dataset, batch_size=bsz, shuffle=True)  # type: ignore[operator]
        opt = torch.optim.Adam(model.parameters(), lr=1e-3)  # type: ignore[union-attr]
        pos_w = torch.full((45,), 39.0 / 6.0, device=device)  # type: ignore[union-attr]
        crit = nn.BCEWithLogitsLoss(pos_weight=pos_w)  # type: ignore[union-attr]
        model.train()
        for _ in range(epochs):
            for xb, yb in loader:
                opt.zero_grad()
                out = model(xb)
                loss = crit(out, yb)
                loss.backward()
                opt.step()
        model.eval()

    def _fit_model(
        draws: list[dict], prefer_cuda: bool, epochs: int
    ) -> tuple["LottoLSTM", str]:
        if prefer_cuda and torch.cuda.is_available():  # type: ignore[union-attr]
            try:
                m = LottoLSTM().to(torch.device("cuda"))  # type: ignore[union-attr]
                _train_on_device(m, draws, torch.device("cuda"), epochs)  # type: ignore[union-attr]
                return m, "cuda"
            except RuntimeError as e:
                if _is_oom(e):
                    torch.cuda.empty_cache()  # type: ignore[union-attr]
                    logger.warning("LSTM 학습 중 CUDA OOM — CPU로 재시도", exc_info=False)
                else:
                    raise
        m = LottoLSTM().to(torch.device("cpu"))  # type: ignore[union-attr]
        _train_on_device(m, draws, torch.device("cpu"), epochs)  # type: ignore[union-attr]
        return m, "cpu"

    def _save_checkpoint(model: "LottoLSTM", trained_len: int) -> None:
        os.makedirs(CKPT_PATH.parent, exist_ok=True)
        torch.save(  # type: ignore[union-attr]
            {
                "model_state": model.state_dict(),
                "last_trained_on": trained_len,
                "formula": CKPT_FORMULA,
            },
            CKPT_PATH,
        )

    def _load_checkpoint() -> dict | None:
        if not CKPT_PATH.is_file():
            return None
        try:
            ck = torch.load(CKPT_PATH, map_location="cpu", weights_only=False)  # type: ignore[union-attr]
        except (OSError, RuntimeError, pickle.PickleError) as e:
            logger.warning("LSTM 체크포인트 로드 실패: %s", e, exc_info=True)
            return None
        if not isinstance(ck, dict) or "model_state" not in ck:
            return None
        if ck.get("formula") != CKPT_FORMULA:
            logger.info(
                "LSTM ckpt formula mismatch (%s != %s) — 구버전 폐기",
                ck.get("formula"),
                CKPT_FORMULA,
            )
            return None
        return ck

    def _predict_on_device(
        model: "LottoLSTM", x1: Any, device: Any
    ) -> Any:
        model.eval()
        with torch.no_grad():
            m_on = model.to(device)
            o = m_on(x1.to(device))
        return o

    def _ensure_model_ready(n_draws: int, d_sorted: list[dict], prefer_cuda: bool) -> None:
        """시점 게이트: last_trained_on > n_draws 인 가중치는 사용·저장 금지."""
        global _MODEL, _LAST_TRAINED_LEN, _DEVICE_USED, _MODEL_EPHEMERAL

        ck = _load_checkpoint()
        disk_len: int | None = None
        if ck is not None:
            disk_len = int(ck.get("last_trained_on", 0) or 0)

        mem_ok = (
            _MODEL is not None
            and ckpt_usable_for_horizon(n_draws, _LAST_TRAINED_LEN)
        )
        if mem_ok and n_draws - _LAST_TRAINED_LEN < RETRAIN_INTERVAL:
            return

        disk_ok = (
            ck is not None
            and disk_len is not None
            and ckpt_usable_for_horizon(n_draws, disk_len)
        )
        if disk_ok and (not mem_ok) and disk_len is not None:
            if n_draws - disk_len < RETRAIN_INTERVAL:
                try:
                    m = LottoLSTM()
                    m.load_state_dict(ck["model_state"])
                    m.eval()
                    _MODEL, _DEVICE_USED = _place_model(m, prefer_cuda)
                    _LAST_TRAINED_LEN = disk_len
                    _MODEL_EPHEMERAL = False
                    return
                except (RuntimeError, KeyError) as e:
                    logger.warning("LSTM state_dict 복원 실패 — 재학습: %s", e, exc_info=True)

        persist = should_persist_checkpoint(n_draws, disk_len)
        epochs = EPOCHS if persist else EPOCHS_EPHEMERAL
        m_fit, dused = _fit_model(d_sorted, prefer_cuda=prefer_cuda, epochs=epochs)
        _MODEL = m_fit
        _LAST_TRAINED_LEN = n_draws
        _DEVICE_USED = dused
        _MODEL_EPHEMERAL = not persist
        if not persist:
            logger.info(
                "LSTM ephemeral fit n_draws=%d disk_len=%s (ckpt 미저장)",
                n_draws,
                disk_len,
            )
            return
        try:
            to_save = LottoLSTM()
            to_save.load_state_dict(m_fit.state_dict())  # type: ignore[union-attr]
            to_save.to(torch.device("cpu"))  # type: ignore[union-attr]
            to_save.eval()
            _save_checkpoint(to_save, _LAST_TRAINED_LEN)
        except (OSError, RuntimeError) as e:
            logger.warning("LSTM 체크포인트 저장 실패: %s", e, exc_info=True)

else:  # pragma: no cover

    def _ensure_model_ready(  # noqa: ARG001
        n_draws: int, d_sorted: list[dict], prefer_cuda: bool
    ) -> None:
        return


def get_lstm_prob_vector(draws: list[dict]) -> dict[int, float]:
    """LSTM으로 1~45 PMF(합≈1.0)을 반환한다. 실패/부족 데이터 시 균등 PMF.

    - 첫 호출 시 torch·체크포인트·(가능 시) CUDA 초기화. 모듈 최상위에서 torch.load 금지.
    - len(draws) < SEQ_LEN+1 이면 균등
    """
    global _MODEL, _LAST_TRAINED_LEN, _DEVICE_USED

    if not _TORCH_OK or torch is None:
        r0 = _uniform_pmf()
        _assert_pmf(r0)
        return r0

    import torch as T

    d_sorted = _sort_by_draw_no(draws)
    n = len(d_sorted)
    if n < SEQ_LEN + 1:
        r0 = _uniform_pmf()
        _assert_pmf(r0)
        return r0

    prefer_cuda = T.cuda.is_available()
    _ensure_model_ready(n, d_sorted, prefer_cuda)  # type: ignore[union-attr, misc]

    assert _MODEL is not None
    m: Any = _MODEL
    win = d_sorted[-SEQ_LEN:]
    seq = [_multihot_from_draw(w) for w in win]
    x1 = T.tensor([seq], dtype=T.float32)
    if _DEVICE_USED == "cuda" and T.cuda.is_available():
        idev = T.device("cuda")
    else:
        idev = T.device("cpu")

    try:
        o = _predict_on_device(m, x1, idev)  # type: ignore[misc]
        result = _softmax_to_dict(o[0])
    except RuntimeError as e:
        if _is_oom(e):  # type: ignore[operator]
            if T.cuda.is_available():
                T.cuda.empty_cache()
            logger.warning("LSTM 추론 CUDA OOM — CPU 1회 재시도", exc_info=True)
            try:
                m_c = m.to(T.device("cpu"))
                _MODEL = m_c
                _DEVICE_USED = "cpu"
                o = _predict_on_device(m_c, x1, T.device("cpu"))  # type: ignore[misc]
                result = _softmax_to_dict(o[0])
            except Exception:  # noqa: BLE001
                logger.warning("LSTM 추론 실패 — 균등 PMF", exc_info=True)
                result = _uniform_pmf()
        else:
            logger.warning("LSTM 추론 RuntimeError — 균등 PMF: %s", e, exc_info=True)
            result = _uniform_pmf()
    except Exception:  # noqa: BLE001
        logger.warning("LSTM 추론 실패 — 균등 PMF", exc_info=True)
        result = _uniform_pmf()

    result = _renorm(result)
    _assert_pmf(result)
    logger.info(
        "LSTM PMF: device_used=%s draw_count=%d last_trained_len=%d",
        _DEVICE_USED,
        n,
        _LAST_TRAINED_LEN,
    )
    return result
