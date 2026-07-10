So, Google just dropped Gemma 4, their
latest open source model, and it is
genuinely a game-changer. For the first
time, you can run a high-quality AI
model completely locally. No internet
connection, no API costs, no limits. And
in this video, I'm going to show you
exactly how you can download Gemma 4,
how you can run it on your own machine,
and then also how you can connect it to
a tool called Open Code, so you can use
this model to help do your work, to help
build things, to help write code, etc.
And this is all fully offline,
completely free, no limits whatsoever.
If you're new around here, hello. My
name is Matt. I've helped thousands of
business owners learn about AI and build
their own software tools using AI. So,
let's get into it, and first, let's talk
about why Gemma 4 is so impressive. Now,
a while ago, I created a video showing
how you could run your own open source
models locally on your desktop. However,
truth be told, unless you had like a
supercomputer or like a 10 grand PC, you
could not really do anything useful with
these models. However,
Google somehow have managed to create a
model that gives you great performance
on your average PC. So, for reference, I
am on a 2024 MacBook Pro,
reasonably good, but nothing special.
I'm also recording a video at the same
time, so bear that in mind
when we look at the performance of it.
Now, let's have a look at some
benchmarks, and we can see that Gemma 4,
the 31 billion parameter version,
massively outperforms all other models
when it comes to performance versus
cost. It is not the best all-out model,
but when it comes to how much resources
it takes to run versus the output, it is
massively superior. We can see here,
like almost double the ROI if you factor
in the cost of it. So, anyway, let's
dive into how you actually use it. So,
first things first, you want to go to
Ollama and download Ollama if you have
not got it already. Simply come to
ollama.com, then click on this button
here, and you can download it. Now, once
you've downloaded it, you'll see
something like this. If you come over to
the right-hand side over here, you
probably will not see Gemma 4. I've got
it already installed, so I I do see it.
But you probably will not see this. So,
we need to do something in order to
download this model onto our local
device. Now, this is about, depending on
which version you go with, about 10 GB.
In fact, let's talk about this. So,
there are different versions of this
Gemma 4 model, and they're generally
down to the size, how many parameters
are in that model. More parameters there
are, more resources it takes to use, the
more space it requires on your machine,
but the better it is. The version which
most people are using is this 4 billion
parameter model. The 31 billion
parameter is the best one, but today
we're going to have a look at the 4
billion parameter version.
Now, in order to install this, we're
going to need to use the terminal. I'm
on Mac, but if you're on PC, it's
virtually the same. So, we have our
terminal open, and since we have Ollama
installed, we can access over our
commands. So, we're going to go Ollama
pull, and then we need the model. So, if
we go over here, we can choose any of
these to download, but simply latest is
the best one to use for most people.
Paste that in there, and then that is
the command you're going to want to run.
I already have it downloaded, so I'm not
going to do this, but you simply press
enter, and it will download the model
for you. It would take, depending on
your internet, maybe like 10 minutes or
so, maybe a bit less, in order to
install this, because it's about 10 GB,
the size of the file. Once you've done
that, you can open back up the Ollama
application, and you come over here, and
you will see Gemma 4. We can select
this, and in fact, let me turn off my
internet, so you can see that it works
with no internet connection. I can say,
"Explain photosynthesis
to me briefly." Send that off, and you
can see it's creating its answer. We are
not connected to the internet, so
everything that it's doing now is
running locally on my machine. I'm also
recording a video at the same time,
which does take up a lot of the same
resources, running a model and recording
a video. You can see here, it's thinking
through what the answer is, and it's
going to give me a response. Here we go.
Photosynthesis is the process that
allows plants, algae, and some bacteria
to make their own food using sunlight.
Yep, sounds good, and you can see it's
giving actually quite a good overview,
and I can say,
"Put this into one sentence." I can't be
dealing with all that nonsense that it
gives me. There we go. One sentence.
Photosynthesis is the process by which
plants use sunlight, water, carbon
dioxide to create their own energy and
release oxygen as a byproduct. Super.
There we go. So, one of the other things
that Gemma 4 has is that it has built-in
image analysis, which means we can
upload an image, and we can ask
questions about that image. So, let me
do exactly that. Let's create a new
chat. Let's grab an image that I
downloaded, put it in there, and I can
say,
"What is this
a photo of?" And send that off. You can
see it's thinking through, and it's
obviously understood what it is. It's
just now creating its answer from its
thinking. "This is a portrait photo of a
cat taken outdoors. The cat is wearing a
distinctive reddish-brown miniature
hat." That is absolutely correct. Let's
have a look at the image. So, there you
go. You can see that is exactly what it
is. Now, this is pretty cool. If you
download and start using this, you're
going to be able to see that this is way
more powerful, way more effective, way
more useful than any other open source
models that you could run on your own
machine previously. Recently, I was just
on a flight, and I downloaded, I think
it was actually Gemma 3 rather than
Gemma 4, to help me learn Spanish whilst
I was on the flight, whilst I had no
internet connection, and "Fui muy útil."
I obviously need a little bit of work
there. But let's move on to the next
section. How can we actually use this to
help us complete our work, to help us
build software tools, to help us write
code? Well, what we can do is we can run
Gemma 4 through Open Code. So, first
things first, we're going to need to
come to the open code.ai website. If you
don't know what Open Code is,
essentially, it's an open source version
of Claude Code, not the model itself,
but the harness that allows Claude to go
off and do like web searches, to access
your files, to spin up different agents
and things like that. So, yeah, the open
source AI coding agent. But it can also
do other things besides coding, such as
interact with your files. I use it to
create like little video snippets for me
and edit my videos. So, yeah, it can do
a whole load of things. Essentially,
open source Claude desktop. So, first
things first, you want to download Open
Code. I've already got it downloaded, so
I won't be doing this. Then the next
thing we need to do is go over to
terminal, and we need to set up Open
Code to use a model which is running
through Ollama. So, the way that we do
this is run a command called Ollama
launch
Open Code. We'll send that off, and you
can see here that it is now recommending
some models to us, and you can see at
the bottom we have all of the models I
have locally. So, I've got Gemma 4. I
also have Claude 3 Code up. So, I'm
going to use Gemma 4, and select that.
Do I want to proceed? Yes, I do want to
proceed, and it's going to launch Open
Code. And here we go. You can see we've
got Open Code running within the
terminal. And this is where I can get it
to build me projects, I can get it to
work with
creating presentation slides for me, is
one thing I do a lot. I can get it to
edit my videos, is one thing that I do a
lot. However, I do not use it within the
terminal, because I just don't like the
UI, and it genuinely makes a difference.
If you don't like using the UI, you
don't get as good a result. So, what I'm
going to do is simply close the
terminal,
terminate that, and I'm going to open
Open Code. And since I went through that
setup, I kind of linked Gemma 4 with
Open Code. We can see down at the bottom
we have Gemma 4 running through Ollama
as [music] being what we're using. And
we can see here that I am not connected
to the internet still. So, I can say
something like,
"Please create me a basic landing page
to sell supplements to
dogs. It should be a single HTML page."
And I'll send that off, and it's
thinking, and this is all running
offline, all running locally, and all
running whilst I'm simultaneously
recording webcam and recording the
screen. So, when you run it, it's
probably going to be a little bit faster
than this. So, here you can see it is
writing that code for me. Now, it is not
as quick as something like Sonic 4.6
running through Claude Code. However,
this is completely free, this is
completely limitless. You're never going
to get a limit saying, "Sorry, you have
to come back at 10:00 p.m. in order to
carry on using Claude Code." You can run
it completely free, completely locally,
when you're on a plane or when you don't
have internet, when you're at a beach or
something. Not sure why you'd be
building website whilst you're at the
beach, for whatever. You can use this.
No limits. It's fully sovereign. You can
do whatever you want with it. Let me let
me hop in here and say that if you want
to learn
to build any sort of software, I have
got you. If you're one of those people
that has great ideas, but previously
couldn't build them, couldn't bring them
into existence, I've created a free
three-day vibe coding course that will
take you from zero to be able to
actually build something for your
business, for your life, that can help
you achieve whatever it is you want to
achieve. I'll leave a link down in the
description. You can go and check it
out, absolutely for free. Anyway, back
to the video. Okay, so here we are. It
took 2 minutes and 29 seconds to create,
and it's given me all of this code here.
I want to ask it to, "Please put this in
a file so I can open it."
So, you can see it's also going to be
able to interact with our files. So,
it's not just giving us text output,
which in this case is formatted in like
a code block, but it can also interact
with our files, so it can actually do
stuff, actually do work on our behalf,
which is really cool. So, here we go.
It's created that file. So, if I open
this file up, and here we go. This is
our landing page. Is it the best landing
page you've ever seen? No, but I gave it
no direction at all. I've not connected
to any
skills in terms of creating something
that looks good. I've not told it
anything. So, we can let it off on the
design front. We can see it's actually
created something for us, which is kind
of cool, and we can prompt this
completely offline, completely for free,
to get it to build something actually
good. And remember, this is the worst
that free open source local models are
ever going to be. I am super excited to
see where this goes in the future,
because I believe that AI sovereignty,
being able to own all of your own
models, run them locally, to own all of
your own data, is the way forward, and
moving away from these big companies.
So, that's it from this video. If you're
interested about learning more about
vibe coding and building your own
software and tools, then I'll leave a
link to that three-day free course down
below, and I will see you in the next
one. Bye-bye.
Okay, so here we are. It took 2 minutes
and 29 seconds to create, and it's given
me all of this code here. I want to ask
it to, "Please put this in a file so