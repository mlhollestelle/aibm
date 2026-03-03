# About AIBM

AIBM is an experimental agent-based travel demand model that uses large
language models instead of statistical utility functions to simulate daily
travel behaviour.

Disclaimer: This project has been developed while I had limited ability to use a computer keyboard, and nearly all code is written by AI. The code contains shortcuts/limitations that I would not have chosen myself. The purpose of this project is mainly a proof-of-concept, not an ideal implementation.

## How it works

...

## Data and study area

...

## Findings

...


Research questions:
* Does an LLM generate realistic results? And how?
* Does a more powerful model generate more realistic results?
* How much do results differ between various runs?
* How sensitive is the model to policy interventions?
* Are LLMs from different providers giving very different results?
* How much does the prompt improve the results? --> Finding that with very vanilla prompts, number of activities is way too high.


Lesson's learned:
* A prompt alone does not to logical day plans. Lot of flexible activities are overlapping the fixed activity. More care to the prompt is needed.
* Prompts alone do not enforce constraints
>  One of the early surprises in building this model was how unreliably LLMs follow hard       
  numerical constraints, even when stated explicitly. After scheduling an agent's mandatory   
  activities (say, work from 08:00–17:00), the model computes the remaining free time windows 
  and tells the LLM: "Only schedule activities within the listed time windows: 06:00–07:59 and
   17:00–23:00." Despite this, the LLM regularly places discretionary activities squarely
  inside work hours — scheduling a shopping trip at 08:30 or a leisure activity from
  09:45–12:00, as if the instruction wasn't there. The model produces output that looks like a
   plausible daily schedule, but doesn't actually respect the constraints it was given. This
  is a known failure mode of smaller, cheaper models (like GPT-4o mini): they're fluent at
  generating realistic-sounding plans but unreliable at enforcing multiple simultaneous
  numerical rules. The lesson: treat LLM output as a proposal, not a guarantee. Any hard
  constraint — like "don't schedule activities during work hours" — needs a deterministic
  enforcement layer on top, not just a sentence in the prompt.


* If you specify a discrete set of alternatives, the LLM will actually obey and choose from the set.
* If you simply ask an LLM  (at least gpt-4o-mini) to generate a daily set of activities, it will generate a lot of activities in a single day, easily 5-8 per person at times. In reality, people understake most likely 1-2 activities. --> Prompt must somehow nudge towards that. --> Possible solution (will be implemented most likely) is to calculate available windows for discretionary activities.
* The model had clearly bluffed that it could pull of the logic of activity scheduling. Yet, in reality, it had build a system which where an agent can travel from home to a leasure activity, while the agent is actually at work at the same time.
* For destination choice, many PoIs are available. Evaluating all of them in a single prompt is relatively expensive. Random sampling is an option but perhaps importance sampling???!!!
* Without any nudging in the prompts - no agent ever chooses public transport as the impedance is so much higher.
* Many activity-based models follow similar structures. Through prompts, you have a lot more flexibility. One example:
    > When agent is planning its day, you can choose first the main activity, and then you can ask: do you want to do something more, or do you want to go home? etc... You can also just batch ask: schedule these activities (but may violate what is actually possible in reality).
* Mimicking human thinking in the prompt can lead to more accurate answers (then simply prompting e.g., "generate three activities").
* Under the hood, the code uses minutes-from-midnight floats, but that does not work well in prompts (https://github.com/mlhollestelle/aibm/pull/37/changes/c52888fe4cb8d532656905db57ea864618b4d2c1).
* LLMs are inconsistent in the format they return, by mixing upper/lower case or switching between underscore and space:

```
  shopping              15:10  15:45       yes  E0274N3875
  Shopping              17:30  19:00        no  E0240N3988
  Eating Out            19:30  21:00        no  E0310N3903
  eating_out      
```


(Or simply changed eating_out to dining_out)

Recommendations for further research:
* There is probably a lot improvement possible, simply by improving the prompts, making them more comprehensive and use reasoning models.
* Now, each agent determines activity schedule individually. Would some joint discussion (e.g., eat home or eat out) be a good addition?



```
=== Agent 99903: 1 tour(s) ===
  Tour 0 (closed):
    E0276N3869 -> E0277N3869  depart=08:00
    E0277N3869 -> E0283N3856  depart=17:00
    E0283N3856 -> E0316N3914  depart=11:00
    E0316N3914 -> E0317N3914  depart=12:15
    E0317N3914 -> E0276N3869  depart=13:30

=== Agent 99904: 1 tour(s) ===
  Tour 0 (closed):
    E0276N3869 -> E0277N3869  depart=08:00
    E0277N3869 -> E0288N3855  depart=17:00
    E0288N3855 -> E0307N3876  depart=13:00
    E0307N3876 -> E0275N3879  depart=14:10
    E0275N3879 -> E0276N3869  depart=17:00

=== Agent 99905: 1 tour(s) ===
  Tour 0 (closed):
    E0276N3869 -> E0288N3856  depart=08:00
    E0288N3856 -> E0277N3869  depart=09:30
    E0277N3869 -> E0279N3895  depart=16:00
    E0279N3895 -> E0289N3861  depart=13:00
    E0289N3861 -> E0289N3854  depart=14:00
    E0289N3854 -> E0276N3869  depart=15:00
```

Why LLMs is a bad idea:
* Expensive
* No idea about distribution of randomness
* [lesson learned afterwards] Enforcing constraings (with cheap models) is very hard.

Why LLMs are a good idea:
* Encapsulate complex logic in a prompt rather than developing complex empirical models
* No behavioural data to estimate models required
* Story-telling through reasoning by the LLMS (or at least, faked reasoning)
* (Include other factors in the choice than simply impedance --> THIS IS NOT YET IMPLEMENTED.)


What is not in the model:
* Population synthesis is extremely simple
* No size variables for destinations
* No costs for travel, nor parking costs or public transport costs

Lessons learned on AI agentic development:
* Oftentimes, Claude could have taken on bigger (scoped) tasks, especially with Opus. But it makes it harder to keep track on the changes, scrutinize results and keep congitively on top of the code base. Atomic changes (and commits) should be prefered. But, you can make first a plan (with claude) to break down in smaller steps and then execute sequentially. 
* "Build a deeply detailed understanding" or sth similar really helps to get the model to understand the details that matter.
* Claude's token usage windows dictate your life. https://claude.ai/settings/usage was my most visited site.
* Things that are hard for you, are not necesarrily hard for Claude. Things easy for you are not necessarily easy for Claude.
* A domain expert agent is actually very good - with Opus!
* Before plan mode, ask claude first to do deep research and write findings (or action plan) in a detailed .md. --> This you can later pass on to cluade again to make a plan (before execution). --> In hindsight also add those md's somewhere in the git repository. Have earlier looked for best practices but found nothing I liked.


