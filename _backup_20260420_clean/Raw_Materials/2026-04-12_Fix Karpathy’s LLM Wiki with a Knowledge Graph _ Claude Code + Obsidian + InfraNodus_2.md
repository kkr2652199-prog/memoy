Last week, Andrej Karpathy, a prominent AI 
researcher, released a super useful framework  
called LLM Wiki that uses LLM to supercharge your 
research. It's a really good framework. However,  
there's a critical piece missing. It's not 
aware of itself. The problem that Karpati  
himself pointed out is that when you interact 
with your standard AI and you upload some files  
and you want to get a result, what happens is 
that it retrieves uh some chunks of text using  
rag retrieval augmented generation and gives you 
the result and then every time you interact with  
this system, it's always going to do the same 
thing and forget what it's done in the past. So  
you don't have a knowledge base that is evolving 
with you. Andrej Karpathy proposed to resolve this  
problem by building so-called LLM wiki which you 
can open in any IDE or Obsidian that basically  
retrieves all your raw papers or notes organizes 
them in a folder which we call raw folder here  
and then it generates a wiki where it lists all 
the concepts and the connections between them  
the main ideas. So it creates an organization 
for your knowledge and then you can use this  
structure to then interact with it and to generate 
insight. The problem with the system however is  
that even though you have the structure you 
still need something to navigate through it  
because if you just ask your LLM to produce the 
results it's going to extract the concepts that  
you have listed the questions the data but then 
it's going to produce the most probable outcome  
because that's what LLMs are trained to do. This 
is where knowledge graphs can be very useful.  
For the last 10 years, I've been working on 
InfraNodus, a knowledge graph visualization tool  
that represents ideas as network and then applies 
graph science metrics to identify the main ideas  
and clusters of them inside, but most importantly 
identify the gaps in your knowledge which you can  
then use to generate new ideas. So, I'm going 
to show you how you can augment this LLM wiki  
with knowledge graphs so that you can generate 
much more pertinent insights and so that you can  
direct your LLM's thinking through that structure 
that it created. I'll just show you a couple of  
things it can do and then I'm going to demonstrate 
how you can set the whole system up from zero. So,  
let me show you here. I have an already prepared 
wiki that I made from my documents on a research  
topic I'm working on. And uh what I did first is 
that I ingested all my papers into the raw folder  
here uh which you can see some papers here, 
some notes that I have on different topics  
and so on. And then I ran the skill that I'm 
going to also make available to you for free  
uh through my GitHub repo. I'm going to leave the 
link in the description to the video below that  
basically ingests all this raw material and then 
generates structured representation of the main  
concepts in those research papers, how they're 
connected to one another. So the main connections,  
some sources that it uses so that you can always 
get back to those sources or add more interesting  
research papers and then systems that it's talking 
about. Okay. So normally what happens here is that  
once you have that wiki created here which is 
a structured representation of your knowledge,  
you could launch claude code inside that folder 
and then start asking questions about it. But when  
you ask questions, what it's going to do is that 
it's going to scan through your wiki, extract some  
concepts, and then produce the most plausible 
response that kind of connects everything  
together. It can be good for some use cases, but 
when you want to generate new ideas, is not so  
interesting because the results are going to be 
quite generic. What I need first, and this is  
where knowledge graphs are very useful, is to get 
an understanding of the structure of this wiki.  
And so for this you can actually use knowledge 
graph of InfraNodus which you can use both from  
your favorite IDE like in this case I use cursor 
maybe you're using anti-gravity you can install  
the extension of InfraNodus here and then when you 
have that folder of concepts for example where I  
have the most important concepts listed that were 
extracted from the research papers I right click  
on it then I click InfraNodus visualize as a 
graph and then the extension which is opened  
in the side bar here is going to visualize to me 
what are the main topics in my research and this  
is very useful because first of all it reminds me 
what are the main ideas inside network theory you  
know then phase dynamics fractal structure but 
also shows me the smaller clusters that I want  
to develop in order to make this whole discourse 
much more coherent so I will focus on the smaller  
ideas like power mechanisms here for example and 
explore them further or frequency modulation and  
so on right so this helps me see what are the 
topics that I need to develop further. But then  
I can also go into gaps and ask it to show me 
some clusters that could be better connected  
and then focus on the connections between those 
clusters to generate new ideas. You can also use  
this plug-in inside Obsidian itself. So here 
for example I have Obsidian and in Obsidian we  
have the InfraNodus plugin. So then I would open 
that same folder concepts and visualize it as an  
InfraNodus graph and then it would show me the 
connections between the ideas that exist in this  
folder give me the same topical overview and also 
I could identify the gaps and then by bridging the  
gaps and using AI to generate research questions 
I can then generate new ideas that bridge those  
different clusters together. So this would be one 
approach that you can use it visually like this or  
you can also go back to cloud and actually use 
the InfraNodus mcp server which is basically a  
connector for your llm to think in terms of these 
graphs so that it would create that same graph  
representation of your content. So I could ask 
okay use InfraNodus generate graph tool to analyze  
the concepts in the wiki concepts folder. Okay. So 
then it would connect to the InfraNodus MCP tool  
which is basically an like an API that connects 
uh this whole content to Infronotus and then it  
extracts the list of the concepts that we have 
listed here as markdown files. Then you see it  
uses the InfraNodus generate knowledge graph tools 
and it's going to give me a similar insight to  
what I visually see. So here again I can generate 
an overview and then I can use InfraNodus to  
identify the main clusters and then ask InfraNodus 
to generate insights based on the gaps between  
these clusters. So that would be one approach 
to use this. You see it runs the tool then it  
generates the analysis and then it will generate 
a response. As you can see here it provides me  
information about the graph structure main topical 
clusters fractal dynamics critical transitions  
process coupling and also information about the 
gaps. So you can use the graphs if you want or  
you can also use the MCP server inside cloud code 
itself. However, an even more advanced approach  
is to add knowledge graphs into the structure of 
this LLM wiki so that instead of just analyzing  
the folders with the external tool, you actually 
integrate knowledge graphs into the process of  
structuring your knowledge. So that skill that 
I made available actually allows you to do that.  
And what it does is that once your wiki is created 
and you generate some ideas from it, then it will  
create a folder InfraNodus where it's going to 
save so-called ontology graphs that I was talking  
about before on my channel which describe the main 
concepts and relations between them. So then later  
if you say want to analyze what's happening in 
this repository in this wiki you can go back to  
Obsidian for instance and then you can open that 
folder InfraNodus and for example if you want to  
see a graph of all the concepts you have here then 
you just click on this and Obsidian InfraNodus  
plug-in shows you what are the main concepts you 
have here and also which of them are disconnected.  
So that can also give you information how you can 
connect them better. So for example, you can see  
like okay, you have synchronization patterns here, 
but they're not so connected to, for example,  
fractal networks. So you select these two and 
then you generate an interesting question that  
can link them together. And this will give you an 
idea for how you can link disconnected clusters  
of your knowledge and make your whole research 
much more coherent and interconnected which can  
be very useful for improving its structure. Okay, 
so this would be another approach how you could  
use it. You generate InfraNodus ontology graphs 
for everything that it does. So it's some kind  
of living memory of what's happening in the system 
and then every time you come back to it claude or  
whatever system you use will have access to this 
system of rules of of how the concepts connect in  
your wiki and then it will be able to extract them 
and generate some interesting ideas from them. So  
that would be another deeper approach where you 
integrate knowledge graphs into the actual LLM  
wiki. Now that I showed you how all of this looks 
like, let me show you how you would actually set  
something like this up. So first I would create 
a new folder on my computer and I would give it  
the name of the research I'm working on. So for 
example, I want to make another one on finance.  
I click create and then I go inside and I simply 
open the empty folder in my favorite programming  
development environment which is cursor in this 
way. All right. So now it's completely empty.  
Then what I do, I open terminal inside here. 
And by the way, you could also do it directly  
through terminal. But what I like is that in 
something like Corsor or if you like anti-gravity,  
you can use anti-gravity. I can actually see the 
file structure on the left. That helps. Then I  
open cloud and because I already installed that 
LLM wiki skill that I'm going to link to in the  
description to the video below, I can then um ask 
it okay use LLM wiki skill to create a repository  
of knowledge on finance that I have. And you can 
even make a general query like that and see how  
it does. Sometimes you will need to tell it where 
it should take the data. Let's see if the skill  
will actually pick it up because I structured it 
in a way where it will ask you questions for how  
to proceed. Here it's asking us shall I use the 
skill lm wiki we say yes. Okay let's use the skill  
and then see what it does. So first of all it's 
asking me okay you want to explore finance that  
this wiki is for just explain to me what you want 
to work on personal investing microeconomics and  
market personal finance trading and strategy. So 
I would say that I would like to work on personal  
investing. I think that will be interesting for 
me. And also trading and strategy. Okay. So then  
let's click next. And you see everything that it's 
going to do. It's going to ask me a question about  
it. And then it tells me, okay, so what kind of 
sources you want to feed? Articles? Yes. Books  
and papers? Videos and podcasts? No. But personal 
notes and data? Yes. Okay. And then it's telling  
me, okay, so what's your end goal for this finance 
week? So I think I want to track and learn. I want  
to support my decisions. And I want to also have a 
living reference. Submit. You see, it provided me  
um with some questions. I answered them. Now I 
click submit answers. It's going to now use the  
skill to structure my knowledge in the best way 
possible. So now while all this is happening,  
it's basically building something from it. And 
here it's telling me, okay, so how many sources  
you want to have? Um let's say 20 to 100 medium. 
Do we need entity pages for individual stocks,  
funds, or companies or people? Yes, let's do 
that. Uh, do you track your own portfolio data?  
Occasionally, and we submit the answers. So, you 
see, every time it's going to build something,  
this skill, it's going to ask you a few 
questions so it can structure its work  
properly just for your particular use case. So, 
here it asks us a few more questions about what  
kind of structure we want and what kind 
of trading strategies we want to have.
We say that we want to provide some sources to it.
And as you can see, it generated a really nice 
structure where we have the raw folder where we  
will ingest all the relevant articles, notes, 
data and books. Then we have the folder where  
this knowledge will be structured. That's what 
I showed you at the beginning with the concepts,  
connections, data, entries and so on. And then 
uh it will have a folder with the output where  
it will generate interesting ideas and even a 
to-do folder so that you can keep track of the  
things that you need to do to this repository. And 
because it's using infronotus under the hood then  
it's going to also have a hidden folder InfraNodus 
where it's going to store knowledge graphs that  
will keep record of all the important connections 
and concepts that you have in this repository of  
knowledge. Now, as you can see, it also generated 
the cloud MD file and agents MD file that's for  
Codex with a description of what this project is 
about and what we want to achieve with it. So,  
that will really help the agents later to generate 
some interesting ideas from it. And also it added  
some technical files to make sure that we can 
uh track the changes that we do to this and  
uh save intermediary versions as well. Now, 
we say okay, we're ready to ingest a source.  
So let's say that we have a source already. 
So I'm going to say yes. Let's let's do the  
source. And then it's going to tell me okay. So 
where do you want to take the source? And I can  
tell it okay I have all my research papers on the 
Dropbox research papers folder. Find everything  
relevant to finance and economics there. And you 
see the claude is very clever in this case because  
it's basically going to search that folder and 
extract the most interesting papers and images  
and other assets I have on the topic of finance, 
money, and economics. As you can see, it says it  
found a lot of material. Now, it's going to sort 
it into tiers of relevance and organize it. So,  
here it's asking us what it should actually 
extract. Core finance, finance and market dynamics  
or everything potentially interesting. I think 
maybe not everything but let's say that we want  
finance and market dynamics around 30 papers. What 
clo is going to do now is going to extract the  
content from those papers extract the content from 
PDFs and transform it into markdown files which is  
very good because then you would be able to open 
it using any text editor and also they would be  
accessible to your LLM because it will basically 
be like plain text. Now it's copying the files to  
my raw folder that all the books are copied here. 
And then like it says here, it's going to create  
wiki pages for these papers in parallel. If we go 
into wiki, we see that now it has the folder with  
sources and it's adding paper by paper into that 
folder. And here we have a summary of the paper.  
We have some key takeaways from each paper, 
some data and evidence and also relevance,  
quotes and links to important concepts and ideas 
that are present in this paper. So it's creating  
an interconnected structure of the main ideas 
that relate to this project which is really  
great and it would take you hours or even days 
to do that manually. Our end goal here is to  
extract some interesting insight. So this is why 
having this structure is going to be very useful.  
What happened now here is that from these papers 
that it found were relevant, it extracted a list  
of concepts and also a list of connections and 
uh that already creates a really nice structure  
for our LLMs to use inside cloud in order to 
generate some interesting insights for us.  
While it's doing this job, we can actually use the 
InfraNodus extension that I have installed into  
my cursor in order to see the content of every 
page that we have generated here. So for example,  
here I have a page on balance of payments. If I 
want to see what it's about, I can rightclick then  
click in front of this visualize as a graph and 
then it will generate for me a really nice visual  
overview of the main ideas in this summary 
of the concept of balance of pay payments.  
It's about capital dynamics, exchange flow, 
investment trends, market insight, and so on. If I  
open the bond one, then if I right click on that, 
I can then visualize the main concepts there. So,  
as you can see, you're actually creating really 
nice visual representation of the main ideas.  
And if I want to see how all of my concepts 
connect, while of course, Claude will create some  
connections for me. If I don't want to rely on AI 
to do that, I can right click on the whole folder,  
then click visualize as a graph. And what's going 
to happen here is that InfraNodus will visualize  
uh all the concepts from all these different files 
and show me what are the most important topics. So  
I can see there's a lot of on bond returns and 
financial flows, but for example, very little  
on equity analysis or regression analysis. And if 
I decide that maybe regression analysis is quite  
important because it will provide me a framework 
through which I can analyze financial data then  
it's going to be quite important and I should 
develop this cluster more. So you see already just  
from this visualization that is happening live as 
LLM is building that knowledge base I can already  
optimize it by understanding which topics I should 
develop more what kind of sources I should seek to  
make that more coherent and interconnected. 
And if I go into the gaps analysis here,  
I can also see which topics are not so well 
connected. And then using this AI advice button,  
I can generate a question which is like an 
advanced prompt that I can feed back to my  
claude by selecting it and pasting it here. 
That will enable clot to understand a little  
bit better how it can develop ideas further. So, 
it's pretty interesting because not only you get a  
really nice visual overview of what's happening 
in your folders as LLM is building this wiki,  
but you can already optimize it by identifying 
the clusters that are underdeveloped and that  
you want to develop further or finding the gaps 
that you want to bridge with new ideas. Actually,  
let me show you how that would work in practice. 
So here I have a gap identified in the folder on  
concepts and if notice shows me that there is 
a cluster on financial flows and on regression  
analysis there is a gap between them. So what I 
can do is I can click on the question here and  
then it's going to find me the statements from the 
folder of concepts that could be better connected  
and here it provides these two statements to 
me. But then there is also the InfraNodus log  
which is basically a prompt that uses the 
underlying graph that I can use to generate  
some interesting insight. So I'm going to copy 
that prompt with the underlying graph structure  
that shows the two clusters and the possible 
connections between them. Then I'm going to  
go to terminal and open another terminal window. 
So the second one launch clo there and say okay  
based on what you see in the concepts folder 
try to think of the connection between these  
clusters and then I paste this structure which I 
copied from the InfraNodus log with the underlying  
graph structure that represents these clusters. 
Then I provide it here and I can also use this  
as inspiration. These are the actual extracts from 
the concept documents that uh contain uh the most  
dense representation of those clusters. And then 
I can also say to claude uh also take this into  
account. Okay. Then I provide the statements 
and then you see now it's going to basically  
use this structural information. So I point LLM's 
attention to the gap that exists. I provided the  
underlying structure. I give it some context and 
then I say okay use the documents in the concepts  
folder in order to generate an interesting idea 
that would connect these ideas together. How does  
regression analysis connect to financial flow? And 
you see it's doing the work. It's extracting some  
relevant concepts from our wiki from the concepts 
themselves analyzing all these documents taking  
this graph structure that uh we we identified 
into account and then now it's going to generate  
an insight for us. Let's see what it generates. 
So as you can see here based on this gap after  
doing some research it identifies a potential 
research question how the critical transitions  
and systemic fragility affect the bop a fix 
models reliability and it tells us do you want  
me to create a connection page or question page 
to capture any of these insights. Yes. Let's add  
the question and add it into to-do list because 
we want to research it further later. Right. So  
now it will use that question that it extracted 
that found the gap identified the gap generated  
an interesting research question and then it's 
going to add that question into our to-dos list  
so that we can later explore it either manually 
or automatically using AI and kind of like focus  
on something which is not yet explored in the 
literature but that touches upon the topics  
that the literature is talking about. So we 
know that we will have uh good quality source  
material to work with but we will actually come 
up with something new and that can be interesting  
for us because we will link these ideas in new 
ways. So here it added this into to-do and if  
we look at the wiki we now see that we have the 
concepts we have connections between some of the  
concepts. We have also important entities and we 
have some research questions that we are adding  
that will enable us to then guide our research 
and explore the connections between the topics  
that are not connected yet. So then we will be 
sure to generate new insights this way. So this  
is how the system works in a nutshell. I know it's 
a lot to ingest, but what I recommend you to do is  
just to install the skill and to try it for one 
of the projects you have so you can test run it  
yourself with your own data and see what kind of 
insights it can generate for you. And if you see  
that you want this model to work differently, you 
can always modify that skill and add some changes  
into it that will suit your workflow better. 
And once you have something like this generated,  
you can interact with it using cloud code 
using your favorite IDE or you can even go  
back inside Obsidian and you will have that 
structure presented here. So you can use the  
more traditional Obsidian structure to navigate 
through this data, visualize the connections  
between different ideas and see how you can link 
them together in new ways. So you have Obsidian  
as a viewer of this information including the 
InfraNodus graph view plug-in or you have a more  
low-level representation here where you use claude 
or your favorite AI in order to interact with this  
data and to generate new ideas from it and you 
have the graph available here which you can use to  
also visualize this knowledge to find gaps inside 
and to see what the main concepts are and how they  
relate to one another and finally you can use the 
InfraNodus MCP server inside cloud code itself in  
order to generate knowledge graphs and to save 
them into the InfraNodus folder so that you have  
an ongoing memory of the conversations you're 
having. So here if I want to create such graph  
I can go back to the first discussion we had where 
it ingested 20 papers on the topic. It says the  
wiki is ready to use open the finance folder as of 
old and then when you start quering it ingesting  
new sources or gap analysis if you like. So for 
example now I can say okay now that this whole  
wiki is ready run gap analysis on it and then 
look what happens here it's basically going to  
do the same thing that I do in the graph when I 
choose gaps but now it's going to read through  
the main concepts that it ingested and then it's 
going to launch the InfraNodus gap analysis tool  
in order to generate uh the clusters that could 
be better connected and then help us generate new  
ideas from them. So you see here it says let me 
run the InfraNodus analysis directly on the wiki  
content to identify structural gaps. So it first 
gathers all the wiki content from all the files  
that it saved into the wiki here. It will then 
create a query for them. Now as you can see it  
created the full wiki text and then it's going to 
use the InfraNodus generate content gaps tool via  
the MCP server that is connected to my cloud code 
and then it's going to generate content gaps based  
on this content and deliver me similar insights 
that I can get also through this visual interface  
either inside the cursor or anti-gravity or 
inside Obsidian as well if I'm using the AI  
questions here that identifies the gaps and then 
generates questions based on those gaps. But here  
the difference is that I don't actually need to 
use the graph. So if I feel uncomfortable using  
the graph interface, I can just delegate all this 
responsibility to my LLM to the MCP server and  
then I'll just have the readym made insights. But 
I find it's important to also demonstrate to you  
how this whole thing works even if it makes it 
a bit more complicated because you know what's  
happening under the hood that it's not going to be 
some hallucination but we're actually performing  
structural analysis here where we identify 
the main topical clusters find the gaps then  
feed those gaps to the model with the underlying 
graph structure and steer its attention to the  
parts that should be better connected so that the 
quality of insights we get are much less generic  
and much more original. So as you can see here, it 
provided me the final outcome of the research it  
made, identified some of the priorities, added 
them into to-do list. So that's the stuff that  
I should be working on to explore these ideas 
further. And then it even created an ontology,  
an InfraNodus graph with all the main ideas inside 
that show how the different concepts that I have  
in this whole wiki relate to one another in 
relation to this particular exploration. So  
that next time when I will be talking to this 
folder through clot code or through any other  
tool uh LLM will have access not only to the whole 
wiki structure but also to all the relations and  
ideas inside and it will have a much more precise 
understanding of how all of these concepts relate  
and also what questions I should be working on 
to have this knowledge evolve further. So let  
me know how this works for you. If you have any 
questions, please ask them in the comments below  
the video. And I hope you find this demo useful 
and I encourage you to try it on your own notes,  
ideas, research papers, books. I think you will 
get really interesting results. I did. Thank you.