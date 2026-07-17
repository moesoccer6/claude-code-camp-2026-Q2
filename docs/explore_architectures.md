1. an agent file referenced files eg. AGENT.md, @~/docs/*.MD

haiku 4.5

Observation: 
- Coding Harness will read local files, not pertaining to the loop, it will take it off task and waste tokens/usage
- The Agent ended up creating a temp file to create a socket connection and execute commands, we shall ber persisting a common interface for the mud eg. mud_manager 
- when it create a rigid script and fails to login, it starts going off task looking for config files, its obvious that its script to login and interface is flawed, a mud_manager would remove this obstacle for small models 

# Explore Agent Architectures
The largest confusion tech professionals have is applying the correct agent solution because many solutions appears to overlap responsibilies.

We will explore multiple agent architecture to determine fit for our agent workload.

## 1. An agent file with referenced files eg. AGENT.md, e~/docs/*.MD
The simplest agent is creating an "agent file" and possibly importing other files that are read conditionally when needed.

We should attempt to create an
agent file and see if it can connect to the MUD and complete a simple goal:
eg. "Find the bakery and list the menu."
We want to use the the smallest and least intelligent model and scale up.

### Technical Observations
created a CLAUDE.md with a simple prompt, and told it will need to manage its own local
memory via simple markdown
files. We provided it with the location of the MUD and the players credentials.

The agent struggled to connect to the MUD.
The agent would attempt to create temporary code files to manage a telnet connection and execute commands.
The agent did not have enough information about Text User Interface of the MUD to login and see its mistakes.


## 2. Agent Skills driven by main agent eg. ~/.skills

A very common way to drive specific functionality is via Agent skills which is an open format for agents adopted by many coding harnesses and agents SDKs.

- execute blanket python scripts