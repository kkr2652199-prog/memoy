/**
 * YouTube 식 시각(빨강 둥근 사각 + 흰 삼각). Unicode 이모지 대체.
 * getYoutubeBrandMarkHtml(className) — 외곽 span에 class 지정
 */
function getYoutubeBrandMarkHtml(className) {
  const cls = (className || "yt-brand-mark").trim();
  return (
    `<span class="${cls}" title="YouTube" aria-hidden="true" role="img">` +
    "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 24 18\" " +
    'class="yt-brand-svg" width="16" height="12" focusable="false" aria-hidden="true">' +
    "<rect x=\"0\" y=\"0\" width=\"24\" height=\"18\" rx=\"4\" fill=\"#FF0000\" />" +
    "<polygon points=\"8.5,4.2 8.5,13.8 18,9\" fill=\"#FFFFFF\" />" +
    "</svg></span>"
  );
}

if (typeof window !== "undefined") {
  window.getYoutubeBrandMarkHtml = getYoutubeBrandMarkHtml;
}
