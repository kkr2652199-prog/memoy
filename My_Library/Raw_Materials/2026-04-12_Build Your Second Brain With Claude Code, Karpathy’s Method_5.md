 Guys, if you want to
 see how to set up Obsidian and
 Claude Code,
 how to do the ingest
 as introduced by Andrej Karpathy,
 keep watching, I'm
 going to show you the setup,
 super easy, then I'm going
 to talk about a few use cases.
 Andrej Karpathy released a concept,
 how you can actually
 create your local RAG using
 code.
 In his example, and in our example today,
 Obsidian as well,
 this post went completely viral.
 So I'm going to walk you
 through how to set it up,
 talk about the benefits, the cons of
 using it and two use cases for a designer
 and a product manager.
 So the concept itself is pretty simple.
 You drop in the raw information like
 articles, PDFs, notes, and
 transcripts, even images.
 Then you ask Claude Code in our example to
 read through it and understand
 assets that it has available.
 And then it creates
 wiki pages out of it.
 Obsidian, as an example, you can use
 tags, you can relate
 different assets together.
 So it's way easier for Claude Code to
 actually go and trace the path.
 In my case, I have used it today to
 analyze and capture my
 transcripts from all the videos.
 What I have also included is
 a bunch of thumbnails, which are also
 linked to those documents, so I can
 at some point analyze the performance of
 each individual
 thumbnail and see patterns.
 I'm going to show you how to set this up.
 This is Obsidian,
 it is actually super easy.
 Once you have everything in
 your raw folder,
 then the
 or in our case, Claude
 Code, is going to create,
 in this case, it
 created a flat list of files.
 In your case, it could be just a bunch of
 subfolders with files
 in those subfolders,
 it creates all of this automatically,
 and they all kind of
 have references to
 raw files, which the LLM
 will never really edit.
 It just references those files.
 The LLM also creates a
 claude.md file that kind of describes
 next time you want to ingest
 new articles, new assets, what to do with
 that so it can actually
 keep adding to the same
 and linking everything together.
 Okay, so the first thing you need to do
 is obviously have Obsidian, so just
 navigate to obsidian.md.
 I'm going to put all the
 links in the description
 as a guide as well and all the links
 to Karpathy's posts and GitHub.
 So just download whatever system you're
 using, download and install it.
 Okay, once you have your
 Obsidian on your machine, let's just
 create a folder.
 So I'm gonna create a new folder.
 And then in this folder we're gonna
 create another one called "raw".
 This is where all the raw data is gonna
 live.
 The first time you open Obsidian, you're
 going to get this kind of a pop-up,
 which is going to ask you to create a new
 vault or you can open a
 folder.
 And this is what we
 are going to use today.
 So I'm going to open that folder.
 So let's open Claude as that folder for
 our vault, so I'm gonna click open.
 Now you can go and customize your
 Obsidian however you want.
 What I just did, I
 just changed the theme to
 a dark theme and I have added terminal
 as the community plugin so we can run
 code inside of Obsidian.
 So now if you look on
 the left hand side this is our
 folder here, so this is the folder that
 is local in the Claude
 folder, subfolder being raw.
 Now it's empty so we need
 to add some documents to it.
 What I'm going to use is I'm going to use
 a plugin or an extension for Chrome
 to actually scrape a website which
 So there's a cool extension for Chrome,
 which is called Web Clipper for Obsidian,
 which lets you
 grab all the
 content from a website and create a markdown file
 automatically in your open vault.
 So to
 use it
 just click Add to Chrome.
 Obviously I do already
 have that but you would
 normally install that in your Chrome.
 It's
 safe and it's used by many people.
 Let's grab this
 from the Anthropic website
 using the Web Clipper.
 If you look on the right hand side here,
 this is where the extension is.
 One thing worth actually changing is the
 actual name of the folder you want the
 information to go to,
 so I'm going to call
 the folder "raw" as it
 is called in Obsidian.
 Also if you were to go to
 settings, you can see that
 the vault setting here,
 currently just says to
 use the opened vault.
 You can specify
 if you have a different vault you want
 this information to be saved
 in, you can specify the name.
 It has to be named exactly
 as the folder is being named.
 I'm going to leave this blank so it knows
 to have an Obsidian open, just use
 the folder called "raw" and just
 store the data there.
 And we are just going to add to Obsidian.
 And as you see, it automatically took us
 to Obsidian to the folder raw.
 And this is our file.
 It is a
 file that is going to be used
 for us to actually ingest
 and create a wiki using
 Karpathy's logic
 and so on.
 And so I'll show you that
 in the next step.
 So, Claude Code has created the markdown file
 which kind of guides the LLM.
 It gives the LLM a lot of
 freedom on what to do actually,
 it describes the core idea,
 how the wiki needs to be structured.
 It also provides the LLM with a few
 tools that the LLM has access to.
 So all you really need to do, and it's
 like, it's super easy,
 you can either just select the entire
 file from here or just click on "Raw".
 That is going to show us the raw text,
 you just
 copy the entire text and
 we go back to Obsidian.
 Start Claude Code here in Obsidian.
 You can use whatever
 you want to use obviously.
 I'm just gonna use
 Obsidian as my IDE today.
 I'm just gonna paste that
 from Andrej Karpathy.
 So this is pasted here
 and then I'm gonna go to my
 prompt that I have created
 which is here in Excalidraw.
 Just select that
 what it says, it kind of guides the
 LLM that you are my LLM wiki agent.
 Build my complete second brain from
 this file. Set up index.md, log.md,
 define the folder structure.
 Walk me through the first ingest step.
 Paste that into Claude
 Code and press enter.
 One thing that you will see
 here, I've got the graph open.
 So this is the actual document
 that is in the raw.
 We just copied from Anthropic.
 And this is the wiki
 it's already building out.
 So you can see
 a bunch of folders,
 analyses, concepts,
 entities, and sources.
 In my case, when I was doing the YouTube
 it took around half an hour
 in my case.
 I'll have a look.
 So it's already doing that.
 Let me actually
 show that.
 So this is our graph.
 And
 once it's done, you're going to see links
 from one file to the other file.
 Okay, so we see the first
 batch of files appearing and
 relationships being created.
 Depending on the content, it's kind of a
 decision, it might be
 up to
 10, maybe 20, 30 files.
 That's what it actually wants to do.
 Okay nice, so it didn't take that long
 because we just had one article.
 We've got a summary as well here, how
 many pages, it created 15 pages
 then it actually
 suggests what to do next.
 So next time you have a,
 grab something new or you have a new
 file, you just type ingest it,
 it's gonna go through
 the entire process again,
 making sure that it links
 the new asset to the current structure and
 also creates the new files and so on.
 Now why is this so cool?
 You can obviously use
 the graph to navigate
 entities or just the folder structure.
 You will see that if I were to, let's say,
 click on the attribution
 graph,
 you will see
 that they actually link to other entities as
 well, so they interlink.
 It kind of works like a
 knowledge graph, obviously.
 And then you can
 actually go and dive deeper.
 Either you or, let's say, Claude or other
 LLMs, because it's not
 really specific to Claude.
 Ideally, it would work in a
 terminal, so like a CLI tool.
 But you can use Codex.
 You can use Gemini,
 whatever you want to use.
 This can be super powerful.
 This is just one file.
 In my YouTube
 vault, I have around 60
 transcripts.
 So it's very comprehensive.
 It also has the context of kind of what I
 want to achieve with this channel.
 There's a bunch of tools that the ingest
 process has access to.
 One of them is lint and the health check.
 If you run, let's say
 the health check, it's going to go and
 look for
 entities that are not
 linked to anything else.
 So that's a very
 useful feature.
 It has something called hot
 cache, which actually saves
 context, so you skip rereading pages.
 So you can
 add one file, and it's not going to go
 through all those files.
 It's just going to ingest
 that one file if you direct the
 LLM to it.
 It can also search the
 web, so the web gap filling,
 And once you have this wiki
 you can really plug this into
 an agent, Cursor,
 Windsurf,
 whatever you want to use.
 It's going to be easy to use as context because
 these are just really
 files when you think about it.
 Obviously, Graph View, which we had a look
 at a second ago, just
 gives you a visual representation
 where you can actually see clusters of
 information, maybe gaps as well visually.
 And then the auto relationships, which is
 obviously available in Obsidian,
 but it just uses that
 at a different kind of
 level, which is very useful.
 Okay, let's talk about pros and cons
 because there are some cons to this,
 or pseudo cons.
 The
 first pro is the zero complex
 infrastructure, it's all local,
 so you know there's no hassle when it
 comes to that, but it's
 slow to ingest large batches,
 depending on how many files you have
 and you want to just start this
 journey, it might take a while.
 The knowledge
 compounds over time, obviously.
 So
 if you make this a habit,
 it doesn't take that long.
 You just keep adding
 assets to it,
 but it doesn't scale when it comes to
 millions of documents, right?
 So if you are kind of in an enterprise
 environment and you actually
 want to have millions of files,
 that could be challenging.
 That's where you would probably use RAG
 and embeddings and all that.
 Now, when you use Claude Code
 or any other CLI tool,
 obviously there's
 going to be way less tokens
 when you do the querying because the
 relationships are already there, the LLM
 doesn't have to go and
 scan the entire folders
 and the entire context.
 That's a huge benefit.
 But the downside to it is
 the first time you do this,
 it obviously needs to ingest,
 it needs to create those links.
 So
 it can be,
 I mean, it's not going to be costly, but
 it is going to cost money, right?
 Now the other pro is that
 you can plug this into
 a Claude project,
 really any assistant that you're using,
 again, Cursor, Windsurf,
 Copilot, whatever you like.
 And the con is that you actually have
 to, you know, you have to have this habit
 to make sure that you are actually ingesting
 new data sets to it.
 Now, two use cases,
 because some of you are either designers
 or product managers
 watching this channel.
 So,
 from a designer's perspective, having
 such a wiki can be super
 powerful for your design work.
 So here are kind of a few ideas what you
 might actually put into this wiki, like
 design system documents,
 component decisions,
 brand guidelines,
 tone of voice, whatever,
 you know, whatever your company
 or business is, that's
 going to be used for the context.
 Then obviously user research notes,
 interview transcripts,
 that's another one
 that could be very useful.
 Figma audit logs, if you have any of
 those, and then critique
 feedback maybe.
 If you have done some
 kind of a design crit,
 that could be also useful.
 Any standards, and then obviously
 UX
 teardowns as well,
 that could be super useful.
 So any context that you can
 add to that wiki,
 I think it's just going to supercharge
 your design decisions and the
 direction, especially when it comes to
 UX and solving problems.
 Not entirely sure about the UI, but
 problems and user experience, 100%.
 I would probably think in terms of like,
 if I am a new person starting in
 this company,
 I should just be able to get that wiki
 and get onboarded super quickly.
 Think about the term done and what
 the term done means in 2026.
 I think when
 it comes to just design and
 design itself, the Figma design, or even
 an application like a POC is
 the only thing that we deliver.
 That has been shipped
 needs to be documented
 and it should be
 accessible to others.
 So anyone should be able to query that.
 And the tribal knowledge is another thing
 that is very
 common in big companies.
 There's a lot of tribal knowledge,
 but I think if all the
 tribal knowledge is in that wiki,
 everyone has access to it and it doesn't
 stay tribal anymore.
 Now from the PM side, I think, and I have
 experienced that, and I don't quite
 understand why PMs are
 not doing that already
 using other
 solutions, maybe like GitHub having one
 repository for all their documentation.
 But what I would probably see is like
 specs, and product specs, like the
 features you're working on now,
 so they're not siloed,
 also the ones that you have
 worked on in the past, right?
 So like product specs,
 PRDs, decision logs as well,
 stakeholder interview
 notes, if you have any,
 sprint retros, meeting
 transcripts, OKRs, obviously,
 metrics, KPI notes related to the
 features as well, then
 the customer feedback, NPS,
 comments and scores maybe,
 and then obviously
 competitor product teardowns and
 positioning.
 And in the same way as the designer, the
 PM should probably also think about like,
 what is the definition
 of done for me in 2026?
 I have shipped this,
 that's cool,
 but what is next, right?
 Like it needs to be documented
 for any other PM to be able to leverage that
 or their own LLM to be able to leverage
 that when they are
 working on the next feature.
 So if it is shipped,
 then the why needs to be saved somewhere.
 The why is probably in the PM's head,
 but it's not documented anywhere.
 It needs to be documented,
 it needs to be in the wiki,
 so others can leverage that.
 When a new product manager joins,
 how do you onboard?
 How do you offload the information so that
 the new PM gets the full context,
 they can query the LLM,
 see what has been done, maybe come up
 with a few more ideas.
 You know, and the teams change, right?
 The memory will survive with a wiki.
 And again, it doesn't have to be this.
 This is an amazing way
 of doing it, but it can be
 anything really.
 It can be in GitHub.
 Just make a habit of storing it in one
 place and you can query it.
 Okay, so one concern you might have,
 because this is local, right?
 How do people contribute to it?
 And obviously
 you can create a repository in GitHub.
 That is probably the
 easiest way to do it.
 And that's what actually I have done.
 So
 the raw files, images, and all the
 wiki that I have created
 for myself, for this YouTube channel,
 is all in my repository.
 So
 if I were to go to my GitHub
 to this repository, it
 is exactly the same thing.
 So you can imagine that if you have a
 group of product managers, group of
 designers, they can just
 contribute to the same
 repository in GitHub.
 And then once you decide to
 use Obsidian,
 for it, you can just ask
 Claude Code, or Codex, whatever CLI, hey,
 check what new files have been added to
 this GitHub repository.
 And that's going to update your local
 version of that repository, which is your
 wiki. Guys, let me know in the comments below
 what do you think about storing all the
 information, company context,
 your design system context, your PRDs,
 all of them, all of them, not just the
 current feature you're working on,
 in one place
 for LLMs to use.
 So
 thanks for watching.
 I'm going to put in the description all
 the links you need to set this up.
 I am going to see you next time.
 Bye.