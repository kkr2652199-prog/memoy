Andre Karpathy just broke the internet
with a new research method that is going
to fundamentally change how we all use
AI. Here's a problem. LLMs suck at deep
research. Sure, they can look at a
couple websites and get you surface
level answers, but when you try and
compare ideas or actually dive deeper,
it all completely falls apart. The
solution is Karpathy's exact system for
doing PhD level research with AI that
creates custom LLM knowledge bases that
actually get smarter over time. In this
video, I'll break down his complete
method on how to build your own LLM wiki
in just 5 minutes for completely free.
And by the end of this, you'll never
have to do research the old way again.
If you're new here, my name is Tommy
Chris and I've been using AI to automate
real businesses for over 2 years. I've
scaled past multiple $10,000 months.
I've worked with companies ranging from
5 to even 500 employees. And so, let's
hop into it. So, the first thing I want
to dive into is where this idea actually
came from, which was this tweet um on
April 2nd from Andre Karpathy. And you
can see it's blown up, has over 14
million views now.
And basically, he was just sharing uh
something that he's found very useful,
which was this idea of using LLMs to
build personal knowledge bases, um which
he calls the LLM wiki. And so, I'm just
going to break down some of the core
components as he describes it here. So,
first in terms of data ingestion, um he
just indexes source documents, which is
a very simple way of he throws text
files, um PDFs, and whatever else he
needs into this and the LLM will
actually categorize it uh and file it
for him. And then, for the IDE, he
actually uses Obsidian as the front end
where he can view all the raw data. Now,
if you don't know what that means, what
that actually looks like practically
is this. It creates uh this little web
where you can connect uh as a wiki
each
data point or each PDF or text file or
image that you create um and see how
they link together. And that way, you're
able to connect different ideas um and
the AI will know which ideas connect.
And so, this was just a quick example I
built um earlier when testing this out.
And the Obsidian platform is completely
free and I'll get to that in a second.
Next, uh in terms of actually querying
the AI to see what answers you can find
and actually reap the benefits of all
this research, um he Karpathy recommends
you actually get uh a ton of articles or
research papers in there. He says over
100 and over um 400,000 words in his own
wiki. And then, you can ask the LLM
agent all kinds of complex questions.
Now, do you need that many articles? Um
no, this is just to show that you can
reach that sort of scale, but also to be
careful if you go, you know, well past
that 250 to 200 articles, you know,
maybe this might not be the best method.
And then, in terms of output, um he
instead of getting answers in the actual
terminal, uh like you would if you query
any
any other AI chatbot, um he likes to
have it actually render the markdown
files for him uh or slideshows. Now,
personally, I don't mind it in the
terminal. This is all just personal
preference. Um linting, I won't go super
deep into that, but this is basically
having the AI uh clean up the entire
wiki for you. You know, as it gets
bigger, there might be certain mistakes,
some things might be outdated. And then,
he talks a bit about any extra tools um
he's thinking about using or any further
explorations. Now, because his tweet
blew up, um Karpathy actually made it
super easy for us to implement this. And
he uh wrote this LLM-wiki.md,
which is basically a big fat prompt uh
that you will plug into your LLM. It'll
actually create the entire wiki for you,
aside from downloading Obsidian and
creating whatever folders you need to
do. But, he does note uh at the bottom
that this document is intentionally
abstract. Um this was just a personal
project for Karpathy that he wanted to
share with a bunch of other people
connected with. So, feel free um to edit
yourself and don't feel like this is all
set in stone. You know, do uh whatever
works for you. But again, if you're not
super familiar with it and you're just
getting started out, this is more than
perfect to start out with. Now, one
thing I do want to mention is that if
you want all the resources in this
video, such as the links to the
LLM-wiki, as well as where to download
Obsidian, I keep all my YouTube
resources in my completely free
community that is linked down below,
Applied AI Academy. And so, if you join,
uh once again, it's completely free, you
can just click YouTube resources here
and you will see um my most recent post
will most likely be this video. If
you're watching a bit later, feel free
to just search up the title of this
YouTube video, um how to do PhD level
research, and then, it will show up
there. And once you find the post, you
can click on here and all the resources
will be linked. Now, our first step is
to actually download Obsidian, which is
this front ender IDE to actually view
all our research. So, all you have to do
is go to uh obsidian.md/download,
um click download for Windows or iOS uh
or, you know, Mac if you're on Mac. And
then, once in, uh you should see a
screen like this. Now, it won't look
exactly like this because you won't have
uh any files in here yet. So, let me
actually manage my vaults and create a
brand new one.
And this, I will just call um
YouTube demo. Then, I'm going to pick a
location for this and I just want to put
this um in my existing Obsidian folder
that I created beforehand.
Now, I'm going to create this.
And you can see, I'll close out of this.
We have a brand new uh Obsidian vault.
Now, we're not going to do anything in
here quite yet, cuz what we're going to
do now is actually open uh whatever your
agentic coding platform is. I use
antigravity. Um I actually use uh Claude
code inside of antigravity. What I'm
going to do is I'm going to open the
brand new folder we just created by
using Obsidian. Okay, so now you can see
I have opened up Claude code in my
terminal. And to set this up, all I need
to do
is go back to this LLM-wiki. I'm going
to copy all of it and then come back
into Claude code, paste that. I'm going
to say,
"Can you set up this LLM wiki for me? I
want it to be based on nutrition
research. And once you've actually set
it up, I'll provide you with a number of
articles to actually include inside of
it."
And now that that's working, let's
actually look for some articles. So, one
other thing Karpathy actually recommend
using was this web clipper by Obsidian.
And basically, what this does is it
allows you to very easily copy and paste
uh entire articles into your LLM wiki.
This is again completely free. Um you
can visit obsidian.md/clipper
uh and just add it to your Chrome
browser. So, I'm creating a wiki on
nutrition research. And I'm going to
look for some of the best diets for
actual cognitive and brain function.
What are the best diets for cognitive
and brain function?
Let's see. We have a um Harvard Health
article here, Northwestern Medicine, uh
and Pacific Neuroscience Institute. So,
those all sound good. So, when you visit
these, what you want to do is come up
here, come to your Obsidian web clipper,
and then, you can see uh you have a
couple options. You can add it straight
to Obsidian, uh you can just copy it to
a clipboard, or you can save it as a
file. Now, uh if I click add to
Obsidian,
it'll open Obsidian for me. It'll
automatically add this as an article
here. Um and we'll have the AI connect
this all after. We can see how easy this
is to grab all this research and let the
AI actually synthesize it. So, I'm going
to do this for a couple more articles
and I'll be right back. So, now what we
can see is actually created um all the
format we need for this LLM wiki.
And what we're going to do now is tell
it to actually start to index everything
we just added um into this folder. So,
you can see in this clippings folder, we
have all of the articles that I added. I
added four here. As well as I downloaded
a PDF um and I'm going to paste the path
in here. And what I'm going to tell the
AI is,
"Could you please take this PDF research
paper, as well as the articles inside of
the clippings folder, and index them in
this wiki, and follow the exact
instructions um I just provided you."
And now that we have Claude code
working, I'll get back to you once
everything's done. Now, there is one
really important thing I want to note
about this actual research method.
And that is something Karpathy mentions
here, which is uh the tedious part of
maintaining a knowledge base is not the
reading or thinking, it's the
bookkeeping, which he goes on to explain
is what the LLM does. But, you can't
just expect to become uh a PhD level
researcher just because you're using
this. Because your job is still really
important. And that is to curate
sources, um direct actual analysis, ask
the right questions, and then distill
that and think about what it means. The
LLM's job is just everything else,
allowing you to focus on the things that
only us as humans can actually do. And
so, I just want to stress that you
should not use this as a crutch, but as
another tool to help you enhance your
research, um you know, lead you to
better conclusions, uh and hopefully
asking great questions. Okay, so as you
can see here, took Claude uh just about
11 minutes, and it has now uh fully
ingested and indexed all five pages. So,
let's actually visualize what this looks
like inside of Obsidian.
So, if we come here, I'm just going to
exit out of both these tabs, then click
over here to open the graph view.
You can see we have this web of
everything we're learning about.
So, you can see this omega-3 fatty acids
actually touch touches a bunch of
different things, as well as leafy
greens. So, those might be a bit more
important. We can sort of gauge from
that. And you can read through all this
as needed. You know, you can click on
any source and will take you
to that next page or .md file.
And you can visualize and edit however
you want. Now, if you actually want to
query anything,
I would hit /clear.
And then I would ask a question.
So, let's say
I am a 21-year-old male
who is fairly active but looking to gain
more lean weight.
What sort of diet would you recommend
for me
based on the research that is available
to you?
So, this is obviously a question
specific to myself. And I want to stress
that this doesn't have to just be
nutrition research. This could be
research for your job. It could be for,
you know, other personal interests of
yourself.
And really, you know, anything where you
are probably already using AI to do
additional research or, you know, find
extra answers, especially if you're
doing it, you know, over a long time
horizon and you're asking a lot of
questions that keep popping up, you
know, month after month, you know, this
is a great option.
And so, we can see it has now created a
diet for me or at least the key foods.
And the power of this is that I can
continue to add more articles, research
papers,
tweets even, you know, really anything I
find that I find interesting or from,
you know, reputable source that I
appreciate on this topic, I can continue
to add it into this folder, you know,
tell AI to index it, and then see if any
new discoveries come from that.
And the other big benefit is through
this free tool Obsidian,
it allows us to actually visualize and
see a lot more under the hood of what's
actually happening with all this
information,
as well as,
clip anything such as this, create a
link.
You know, we really don't need this. And
so, I could go in and delete this file.
And so, thank you guys so much for
watching this video.
Please tell me in the comment section
how you actually like this research
method and if you actually find any
additional use cases for it or little
tweaks that you think helps you out. So,
well, if you'd like to work with me and
my company at Rose AI, feel free to book
a call down below. I'll see you in the
next video.