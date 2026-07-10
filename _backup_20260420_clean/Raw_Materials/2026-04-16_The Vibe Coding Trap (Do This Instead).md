It's 2:19 a.m. Your website is [music]
down, your boss is calling, thousands of
customers can't access your site. But
the thing is, you didn't actually write
any of the code. AI did. So, you open up
Claude code and you type, "The site is
broken. Fix it, please."
Of course, this gets you nowhere.
Complaint emails are still flooding in,
and this is where you start to feel the
void open up and swallow your soul. And
you wish that you never heard the term
vibe coding before. This is the
nightmare of anyone that has ever
shipped a project with AI. However, my
thesis is that vibe coding is not the
problem here. And today, we're going to
be having the real conversation that we
need to be having around vibe coding.
Not should you be using it, because that
ship has already sailed. You should be
using it. The question is, how? And the
answer depends entirely on who you are.
Now, this video's going to be a little
bit contentious, so I look forward to
seeing all the interesting comments down
below. But let's start with a scenario
that everyone is panicking about. So,
let's say that a developer is building a
hotel booking platform. Availability
checks, room lookups, like price
calculations. They use AI to generate
all of the core logic. It looks clean,
they run the tests, the tests pass, and
they ship it. Launch weekend comes
around, and a travel blogger posts about
the website. Traffic spikes, the server
buckles. Every availability check is
hitting the database fresh. No caching,
no optimization, full table scans on
every single request. With 20 users when
in testing, this was absolutely fine.
But with 2,000 simultaneous visitors,
it's a bonfire. Your company's phones
are ringing, bookings are failing, and
the window [music] to capture that
traffic is closing by the minute. And
when they dig into it, the developer's
honest answer is devastating. "I didn't
really think about what happened when a
lot of people use it at the same time."
Now, this is a real failure. Things like
this happen all the time. But what
nobody's asking here is where did it
actually go wrong? It's not when they
used AI, but it's when they stopped
thinking about it. The AI didn't hide
the caching problem from them. It just
didn't volunteer it. And because the
developer outsourced the thinking along
with the typing, they never had the
conversation with themselves where they
asked, "What does this look like under
real load?" That's the failure mode. Not
[music] vibe coding, but vibe thinking.
There's a quote that I love by Brian
Kernighan that says, "Debugging is twice
as hard as writing the code in the first
place. So, if you write code at the
limit of your understanding, you can't
debug [music] it." And this is what this
actually means for developers in 2026.
The real time in software development
has never been in the writing of the
code. I know this cuz I've lived it. The
most valuable moments as a developer
that I had weren't when I was typing
away, writing the code, and putting the
semicolons on the end. It was when I was
sitting back, looking out the window,
having a coffee, and thinking through a
problem. That is where the actual most
valuable work happened. The code was
pretty much the easy bit. When it comes
to debugging a distributed system at
3:00 a.m., it requires intuition. The
kind where you look at a stack trace and
your gut says, "Hmm, this feels like a
connection pool issue, right?" That
intuition only comes from genuinely
understanding your system. [music] Not
just the code, but the whole thing. How
everything connects together, how all
the pieces go together, where the
pressure points are, what is likely to
break first under load. If you're a
developer using vibe coding methods,
that is still your job. You don't get to
outsource the thinking, you get to
outsource the typing. And this is a
crucial distinction. We're seeing this
in the real world with companies like
Square, where their senior devs aren't
being replaced, the junior devs are. The
senior ones are staying because they're
the ones that can use AI most
effectively. They ask for the best three
approaches to help solve a problem,
evaluate them with their 20 years worth
of experience, and then pick the right
one for that context. What used to take
a team of six now takes one person with
a deep understanding and the right AI
tools. Most people think AI is a threat
to developers? No, no, no. It's more
leverage. Now, this is where the
conversation gets interesting, because
we've just been talking about
developers, but what about everyone
else? For most of history, or the last,
you know, 100 years, 70 years, whatever
you class the history of software as,
software has been locked behind a wall.
You had an idea, maybe you had a
business problem or like a workflow that
you wanted to automate,
>> [music]
>> or a tool that didn't exist yet. And
unless you had the budget to hire a
developer or the years that it takes to
become one, then that idea just stayed
in your head, and it didn't go anywhere.
However, that wall has gone. A small
business owner in rural Portugal built
herself a custom inventory system last
year. [music] She had never written a
line of code in her life. It's not
perfect, they're rough edges, but it
does exactly what she needs. It costs
her nothing, and she understands it
because she built it, and she knows all
of the systems and all of the CRMs and
everything that it connects to. Did she
need to understand database
optimization? No. Did she need to know
what a race condition is? Also, no. The
stakes are different and the context is
different. Your alternative wasn't
building it properly, your alternative
was don't build it at all. This is the
thing that a lot of the critics on X
miss. They are comparing vibe coding to
professional software development. But
for most people, the comparison isn't
between vibe coding and rigorous
engineering, it's between vibe coding
and just nothing. And this is what it
unlocks. Think about a teacher who
builds a little custom quiz for her
classroom, or a physio who automates his
patient intake form, a founder who can
prototype her idea over a weekend before
she's even raised a penny or talked to
anyone about her idea, or a kid in Lagos
who builds a local logistics app because
he sees a problem that no one else is
solving. Vibe coding is democratizing
technology in a way that nothing since
like the internet has really done. It is
completely lowering the bar for what it
takes to build an application and take
an idea and put it into the real world.
And yes, some of those builds will be
brittle. Some of them will break. Some
of them will have bugs that a senior
engineer would wince at. But, they
exist. [music] They're doing something.
They're creating value that previously
wasn't there before. And that is what
matters. So, that's my take. And those
are the two frameworks, two types of
people, two completely different
conversations. If you're a developer,
vibe coding is a powerful tool. Use it.
Let it write boilerplate. Let it show
you three ways to implement something.
Let it generate the tests. But, own the
architecture. Own the critical paths.
Own the debugging. Then when something
breaks at 3:00 a.m., you need to be the
person who can read the stack trace and
know where to look. AI can help you
write the code, but it can't give you
the mental model of your own system.
That part you still need to understand.
And for everyone else who is not a
developer, then vibe coding might be the
most powerful thing that's happened to
you professionally in the last decade.
Use it with enthusiasm. Build things,
break things, iterate. The ceiling you
thought existed of, "I'm not technical,"
is lower than it ever has been. The
question isn't whether you're technical
enough, the question is like whether
you're curious enough to start using
this and start breaking things and to
start learning. If you're a developer,
you cannot use AI as a way to avoid
understanding what you're building. The
hard thinking is still your job. The
mental models, the architecture
decisions, the debugging intuition, none
of that gets outsourced. Otherwise, you
will hit a ceiling fast when something
breaks and you need to debug something.
But if you extend that warning to mean
that nobody should build with AI unless
they fully understand every line of
code, then you've just like rebuilt that
wall that AI has just knocked down. And
I don't think we should rebuild that
wall. The best developers that I know
are using AI the same sort of way that a
great carpenter uses a power saw. They
didn't stop like understanding wood and
how the grain flows and works. They
didn't stop understanding how joints
work or like where the grain splits or
how to fix something when it goes wrong.
They just stopped spending their time on
the part that the tool does faster.
That's the move. Understanding more,
typing less, thinking harder, building
faster. Vibe coding isn't the enemy,
vibe thinking is. Now, if you are in
that second camp of people, people who
always had great ideas, but not the
experience in terms of coding experience
or the budget to hire developers in
order to take that idea and put it into
the real world, then I've got something
special for you. I've just launched a
free 3-day vibe coding course that will
take you from absolutely zero experience
at all to actually building your first
bit of software. I truly believe this is
one of the most powerful and useful
skills to have right now. So, I will
leave the link to that down in the
description. I'm super excited for you
to check it out. Now, I'm sure a lot of
you won't agree with me, so put all your
comments down in the description. I look
forward to going through them. I'll see
you in the next one. Bye-bye.