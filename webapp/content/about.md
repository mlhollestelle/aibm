# What Happens When You Replace Transport Models With LLMs

Traditional travel demand models predict how people move through cities
using utility functions estimated from survey data. These models are
well-understood, reproducible, and grounded in decades of behavioural
research. They also require enormous amounts of data, specialised
software, and months of calibration work.

What if you skipped all of that and just _asked_ an LLM to make the
decisions instead?

This project — AIBM — is an experiment in doing exactly that. It is an
agent-based travel demand model where every behavioural choice is made
by an LLM prompt rather than a statistical model. It is a proof of
concept, not a production system. The results are messy, revealing, and
— I think — genuinely interesting for anyone thinking about where AI
meets planning.

**What this post covers:** I will explain why I built this, how it
works, what Walcheren (the study area) looks like, what I have learned
so far about LLM-generated travel patterns, and what surprised me about
developing with Claude Code. If you are a transport modeller, the
methodological findings should be relevant. If you are a developer or AI
enthusiast, the LLM behaviour patterns and agentic coding lessons should
be interesting on their own.

---

## Why build this

### The case for LLMs in transport modelling

Activity-based travel demand models work by simulating individual people
making sequences of decisions: where to work, what activities to do
after work, which mode to use, which route to take. Each of these is
typically handled by a statistical sub-model — often a discrete choice
model (logit formulations for mode and destination choice, hazard models
or rule-based systems for scheduling and activity generation), with
parameters estimated primarily from household travel diary data.

Building these models is expensive. You need detailed household travel
surveys, land use data, employment and establishment data, network data,
and substantial expertise in econometrics. Calibration alone can take
months. For many cities, especially smaller ones, this data simply does
not exist.

LLMs offer a provocative alternative. They have absorbed vast amounts of
text about human behaviour, daily routines, and spatial reasoning. When
you describe a 35-year-old employed parent living in a suburban
neighbourhood and ask "what would this person's day look like?", the
answer is often plausible. The LLM is not estimating utility parameters
— it is drawing on patterns absorbed from an enormous corpus of human
behaviour descriptions.

This means you could, in theory:

- **Skip the survey data entirely.** The LLM brings its own behavioural
  priors.
- **Encode complex behaviour in natural language** rather than
  mathematical utility functions.
- **Get narrative explanations** — the model can produce a story for
  _why_ an agent chose to drive instead of cycle. (Whether this
  constitutes real interpretability is another question — see findings
  below.)
- **Prototype quickly** — changing a prompt is faster than re-estimating
  a choice model.

### The case against (for now)

Before anyone gets too excited: there are serious problems with this
approach, and this project surfaces many of them.

- **Cost.** Each agent requires multiple LLM calls. A run of just 10
  households already hits rate limits. Scaling to a city-wide model of
  thousands of households would cost a lot at current API prices.
  [Placeholder: insert actual API cost per household and projected cost
  for full Walcheren population]
- **No distributional control.** A calibrated logit model gives you a
  known probability distribution over choices, with estimated
  coefficients that tell you exactly how sensitive each choice is to
  each attribute (e.g., a one-minute increase in travel time reduces
  mode probability by X%). An LLM gives you a single sample from an
  opaque distribution. You have no control over the variance, no
  elasticities for policy analysis, no way to guarantee that aggregate
  mode shares match observed data, and limited ability to do sensitivity
  analysis.
- **Constraint violation.** LLMs — especially cheaper ones like GPT-4o
  mini — are unreliable at enforcing hard numerical constraints, even
  when you state them explicitly. More on this below.
- **Reproducibility.** Even with temperature set to zero, LLM outputs
  are not deterministic across API versions (or even within the same
  version, due to GPU floating-point non-determinism). The same prompt
  may give different results next month.
- **No feedback loops.** Traditional ABMs and agent-based simulations
  like MATSim include feedback: agents revise plans based on experienced
  congestion or schedule delays. This model is a single-pass generation
  — no iteration, no learning from network conditions.
- **Validation is hard.** Without ground-truth survey data for the study
  area, it is difficult to say whether the LLM- generated patterns are
  "correct" — only whether they are plausible. A reasonable benchmark
  would be comparing against OViN/ODiN national travel survey marginals
  stratified by urbanisation level.

### Personal context

I should mention how this project came about. I was on sick leave and
could only use one hand. Traditional coding was out of the question.
Instead, I used Claude Code with Whisper voice-to-text to develop the
entire project — dictating instructions and having the AI write
essentially all of the code. This shaped the project in fundamental
ways: it had to be buildable through conversation, not through the kind
of rapid keyboard-driven iteration I am used to.

The limitation turned out to be a feature. It forced me to think in
terms of high-level instructions and clear abstractions, which is
arguably a better way to build software anyway. But it also meant
accepting shortcuts and simplifications that I would not have chosen
under normal circumstances.

---

## The study area: Walcheren

### Why Walcheren

Walcheren is a peninsula in the province of Zeeland, the Netherlands. It
contains three municipalities — Middelburg, Vlissingen, and Veere — with
a combined population of roughly 115,000 people.

I chose it for three reasons. First, Middelburg is my home town and I
know the area well, which makes it easier to sanity-check results.
Second, Walcheren is spatially contained — it is nearly an island,
connected to the mainland by a single road corridor. This makes it a
clean study area with limited boundary effects. Third, it is small
enough to be computationally tractable for an LLM-based model.

### Data

All input data comes from open sources:

| Data                                | Source                              |
| ----------------------------------- | ----------------------------------- |
| Municipality boundaries             | CBS / PDOK (Dutch national geodata) |
| Population and household statistics | CBS 100m grid (2024)                |
| Road network                        | OpenStreetMap via osmnx             |
| Points of interest                  | OpenStreetMap via Overpass API      |
| Transit routes (bus, train, ferry)  | OpenStreetMap via Overpass API      |

The spatial unit is the CBS 100-metre grid cell, identified by easting
and northing hectometres (e.g. `E0276N3869`). There are roughly
[placeholder: number of inhabited zones] inhabited cells in the study
area.

### Simplifications

The synthetic population is deliberately simple. Each grid cell
specifies household counts and age distributions from CBS data, but
employment rates, vehicle ownership, income distribution, and driving
licence rates all use national-average defaults rather than locally
calibrated values.

There are no destination size variables — zones are not weighted by the
number of opportunities they contain. There are no travel costs — no
parking charges, transit fares, or fuel prices. These are significant
omissions that would matter in a real planning application, but
acceptable for a proof of concept focused on the LLM decision-making
itself.

---

## How the model works

The pipeline is a Snakemake workflow with 14 steps. The interesting part
— where the LLM enters — is the simulation step. Here is what happens
for each agent:

### 1. Persona generation

The LLM writes a one-to-two sentence behavioural profile for the agent
based on their demographics. For example: _"A 42-year-old employed
parent with a driving licence and two household vehicles. Lives in a
residential neighbourhood in Middelburg."_ This persona is injected into
every subsequent prompt to maintain consistent "character."

### 2. Location choice (work/school)

Employed agents and students need a fixed daily destination. The LLM
sees 12 randomly sampled candidate zones, each with travel times by all
available modes, and picks one. The sampling is uniform — no gravity
weighting — to avoid mechanically biasing the LLM toward nearby zones.

### 3. Activity generation

The LLM lists discretionary activities for the day: shopping, leisure,
personal business, eating out. Mandatory activities (work, school) are
always included for relevant agents. Each activity is flagged as
flexible or fixed.

### 4. Scheduling

Mandatory activities are scheduled first. The model then computes free
time windows and presents them to the LLM for discretionary activity
placement. This two-pass approach was a hard-won lesson (see findings
below) — but it turns out to mirror a well- established principle in
activity-based modelling: mandatory activities serve as temporal "pegs"
around which the rest of the day is organised. Models like DaySim and
CEMDAP use the same hierarchical structure.

### 5. Destination choice for discretionary activities

The LLM sees sampled POIs with travel times and picks destinations for
each flexible activity. Destination and time-of-day choice happen
together in a single prompt to avoid temporal conflicts.

### 6. Mode choice

For each tour (a home-based chain of trips — leaving home, visiting one
or more destinations, returning home), the LLM picks a single travel
mode for the entire tour. This tour-based mode choice is a deliberate
design decision: it reflects the real constraint that if you drive to
work, you need your car to get home. Car is only offered if the agent
has vehicle access. The LLM returns a short narrative explaining the
choice.

### 7. Household coordination

At the household level, the LLM handles vehicle allocation (when there
are fewer cars than drivers), escort trips (children under 12 cannot
travel alone), and joint activities (shared household outings).

After simulation, trips are assigned to the road network using
all-or-nothing shortest-path routing — each trip loads onto its shortest
path with no capacity constraints or congestion feedback. This is the
simplest possible network loading. There is no supply-side equilibrium,
no land-use feedback, and no iteration between demand and network
conditions.

_Recommended graph: A flowchart showing the seven LLM decision points,
with arrows indicating which prompts feed into which subsequent
decisions._

---

## Findings

**A note on sample size:** The current model runs 10 households (roughly
25 agents). At this scale, no aggregate statistic is meaningful — these
are qualitative observations about LLM behaviour, not statistical
conclusions. Scaling up is needed before any of these findings can be
quantified with confidence.

### LLMs do not respect constraints

This is the single most important finding. When the LLM is told "only
schedule activities within these time windows: 06:00–07:59 and
17:00–23:00," it routinely places shopping trips at 08:30 or leisure
activities from 09:45–12:00 — right in the middle of the working day.

The output _looks_ like a plausible daily schedule. It just does not
actually respect the constraints it was given. This is a known failure
mode of smaller models (GPT-4o mini in particular): they are fluent at
generating realistic-sounding plans but unreliable at enforcing multiple
simultaneous numerical rules.

The lesson: **treat LLM output as a proposal, not a guarantee.** Any
hard constraint needs a deterministic enforcement layer on top, not just
a sentence in the prompt.

_Recommended graph: A timeline visualisation showing a few example
agents where the LLM scheduled activities that overlap with mandatory
work hours, before and after the two-pass fix was applied._

### Too many activities without nudging

Without careful prompting, the LLM generates 5–8 discretionary
activities per agent per day. In reality, Dutch travel survey data shows
most people undertake 0–2 discretionary activities on a given weekday —
and 15–20% of the population does not leave home at all. The LLM never
generates a stay-at-home day. It seems to optimise for an "interesting"
day rather than a realistic one.

The fix was to compute available time windows after mandatory activities
and present only those gaps to the LLM, combined with explicit guidance
about typical activity counts.

_Recommended graph: Histogram of activities per agent, comparing an
early "vanilla prompt" run against the current constrained version, with
a reference line for typical observed values from Dutch travel survey
data (OViN/ODiN)._

### Nobody takes public transport (without nudging)

In early runs, zero agents chose transit. The impedance (travel time
including walking to stops and waiting) was always much higher than car
or bike, and the LLM made the rational individual choice to avoid it.

This is actually a realistic reflection of revealed preference in many
Dutch cities outside the Randstad — but it also highlights that the LLM
has no built-in mechanism for policy-driven mode share targets. In a
traditional model, alternative-specific constants (ASCs) absorb
unobserved mode preferences and are calibrated to match observed
ridership. The LLM has no equivalent calibration lever — it simply
reflects what it considers "obvious."

[Placeholder: describe what nudging strategy was used and whether it
produced more realistic transit mode shares. Possible test: run the same
population with and without a transit-encouraging prompt and compare
mode shares.]

_Recommended graph: Mode share bar chart across multiple runs with
different prompt strategies (vanilla, transit-nudged, car-restricted)._

### Format inconsistency

LLMs mix casing and naming conventions freely. The same activity type
appeared as `shopping`, `Shopping`, `Eating Out`, and `eating_out`
across different agents in the same run. The model even renamed
`eating_out` to `dining_out` unprompted.

This required a normalisation layer — something a traditional model
never needs because choice alternatives are coded numerically.

### Clock time works better than minutes-from-midnight

Internally, the model uses minutes-from-midnight floats. Early prompts
exposed these raw numbers to the LLM. Switching to HH:MM string
formatting in prompts immediately improved the quality of time-related
outputs. LLMs understand "08:30" better than "510.0."

### Discrete choice sets work

When the LLM is given a defined set of alternatives — activity types
from a fixed list, zones from a sampled set, modes from an
availability-filtered list — it reliably picks from that set. The
structured output / JSON schema enforcement available from most
providers makes this robust.

The problems arise with continuous or semi-continuous constraints (time
windows, durations) rather than categorical ones.

### The LLM defaults to the fastest mode, ignoring its own persona

In the walkthrough notebook, all three agents in a test household were
given transit-oriented personas — "relies on public transport," "heavy
public transport and walking user," "prefers nearby amenities on foot."
When it came time to choose a mode, every single one chose bike. The
reasoning? "Weather seemed nice," "saves energy," "more efficient
schedule." The LLM rationalised the fastest option with
plausible-sounding explanations that contradicted the persona it had
been given just a few prompts earlier.

This is a fundamental tension: the LLM generates a nuanced persona but
then ignores it when making a concrete choice where travel time
dominates. It optimises locally (shortest trip) rather than maintaining
character consistency.

_Recommended graph: A scatter or table showing persona keywords versus
actual mode chosen, highlighting the disconnect between stated
preference (persona) and revealed preference (mode choice)._

### Everyone starts work at 9:00

In the test run, all three employed/student agents were scheduled to
start at 09:00. A real population shows a distribution of start times —
07:00 to 10:00 with a peak around 08:00–08:30 in the Netherlands. The
LLM defaults to the culturally dominant "nine-to-five" pattern,
producing unrealistically peaked morning departures. This is likely a
subtle form of cultural bias: Dutch work start times skew earlier than
the Anglo-American norm that dominates the LLM's English-language
training data.

[Placeholder: test whether adding explicit guidance like "vary start
times realistically" or providing a distribution in the prompt improves
temporal spread.]

_Recommended graph: Departure time histogram from a larger run (50+
agents) compared against OViN/ODiN observed departure distributions._

### Joint activities create scheduling conflicts

When the household coordination step proposed joint activities (shared
shopping trip, dinner out), these were added to each agent's day plan
alongside their individual discretionary activities. The result: Agent
99903 ended up with both an individual eating-out at 17:30 and a joint
shopping trip at 17:30 — the same time slot, double-booked.

The LLM does not automatically de-duplicate or resolve conflicts when
combining plans from different decision stages. This is another case
where deterministic post-processing is needed.

### The LLM over-weights proximity in location choice

When choosing work or school zones from a set of 12 candidates, all
agents picked among the closest options by travel time — even when more
distant zones had significantly more POIs and might represent more
realistic employment centres. The LLM appears to have a strong proximity
bias, effectively recreating a steep distance-decay function without
being asked to.

This is not necessarily wrong — people _do_ prefer shorter commutes —
but the effect seems stronger than what calibrated gravity models
typically produce. The LLM does receive POI counts for each candidate
zone, so size information is partially present. But it still
over-weights proximity — suggesting its implicit distance-decay is
steeper than typical calibrated models.

_Recommended simulation test: Compare the LLM's implicit distance-decay
curve against a standard gravity model calibrated to Dutch commuting
data._

### The LLM provides explanations (sort of)

One genuinely useful feature is that the LLM can explain each choice in
natural language. An agent might say: _"I chose to bike because the
weather seemed nice and work is only 12 minutes away."_ These
explanations are visible in the web app.

Whether these explanations reflect the LLM's actual "reasoning" or are
post-hoc rationalisations is an open question. But for communication and
stakeholder engagement, having a model that can narrate its own
decisions is compelling.

[Placeholder: include 2-3 particularly interesting or amusing mode
choice explanations from actual model runs.]

### How do results compare across LLM providers?

[Placeholder: This is an important comparison that has not been done
yet. Running the same scenario with GPT-4o mini, Claude Haiku, and
Gemini Flash would show whether the "behavioural priors" baked into
different LLMs produce meaningfully different travel patterns.]

_Recommended simulation test: Run identical population with 3 different
LLM providers. Compare mode shares, average trip lengths, activity
counts, and temporal distributions._

### How sensitive is the model to prompt variations?

[Placeholder: Systematic prompt sensitivity analysis has not been
conducted. This would be valuable — small changes in prompt wording may
significantly alter aggregate results, which would be a major concern
for any planning application.]

_Recommended simulation test: Create 3-4 prompt variants (e.g.,
different persona styles, different scheduling instructions) and compare
aggregate outputs. This tests the "stability" of the approach._

### Run-to-run variability

[Placeholder: How much do aggregate results differ between repeated runs
with the same inputs and prompts? Unlike Monte Carlo variance in
traditional models — which is well-understood and can be reduced by
increasing the number of draws — the LLM's run-to-run variance has no
theoretical basis. You do not know whether more runs will converge to a
stable mean.]

_Recommended simulation test: Run the same 10-household scenario 5-10
times. Report the coefficient of variation for key outputs (mode shares,
average trip length, total VKT)._

---

## Future development ideas

- **Prompt engineering for realism.** There is almost certainly room to
  improve results through better prompts, especially using reasoning
  models (o1, Claude with extended thinking) that can work through
  scheduling logic step by step.
- **Gravity-weighted destination sampling.** Currently, candidate zones
  are sampled uniformly. Weighting by distance or opportunity count
  would give the LLM a more plausible choice set.
- **Calibration against observed data.** Using Dutch national travel
  survey data (OViN/ODiN) to assess whether LLM-generated mode shares,
  trip lengths, and activity patterns are in the right ballpark.
- **Cost in the choice set.** Adding parking costs, transit fares, and
  fuel costs to mode choice prompts.
- **Inter-agent conversation.** Currently each agent decides
  independently (except household coordination). Could agents "discuss"
  plans — for example, a household debating whether to eat at home or go
  out?
- **Scaling experiments.** How far can you push the number of households
  before cost and rate limits make it impractical? What is the minimum
  sample size needed for stable aggregate results?
- **Policy testing.** The real test of any transport model is whether it
  responds plausibly to policy interventions. What happens if you add a
  congestion charge? Remove a bus line? Build a new bike path?
- **Hybrid with MATSim.** An intriguing direction: use LLMs to generate
  initial day plans, then feed them into MATSim's iterative
  co-evolutionary framework where agents revise plans based on
  experienced network conditions. The LLM proposes, MATSim evaluates and
  refines.

# Conclusions (JUST A BRAIN DUMP)

- Even when improving the prompt to get to closely realistic results, it
  is really hard to make sure you get a model that behaves realistically
  and intuitively. Statistical analysis on emprical data may be still
  needed to at least validate the model thoroughly before putting the
  model to use.
- Will it ever be possible? Not sure? [TAKE CONCLUSIONS FROM PAPERS AND
  REFLECT ON OWN EXPERIENCE.]

---

## Developing with Claude Code: lessons learned

This project was built almost entirely through AI-assisted development —
primarily Claude Code with voice input via Whisper. Here is what I
learned.

### Atomic changes matter more than you think

Claude (especially with Opus) can take on large, ambitious tasks. But
bigger changes are harder to review, harder to understand, and harder to
roll back when something goes wrong. I learned to break work into small,
focused changes and commit frequently. The pattern that worked best: use
Claude to make a plan, break it into steps, then execute each step as a
separate conversation.

### Things that are hard for you are not hard for Claude (and vice versa)

Writing boilerplate, wrangling data formats, setting up test scaffolding
— Claude handles these effortlessly. But tasks requiring sustained
logical consistency across a long context (like ensuring a scheduling
algorithm never produces time conflicts) were surprisingly error-prone.
The model confidently produced code that _looked_ correct but violated
invariants in subtle ways.

### Domain expert agents are genuinely useful

Claude Code supports custom sub-agents. I used a travel demand expert
agent (powered by Opus) to review methodological decisions — and it
caught real issues that would have taken me much longer to notice.

### Token limits dictate your workflow

The single biggest constraint was not capability but capacity. Claude's
context window and rate limits shaped when and how I could work. The
usage dashboard became my most-visited page.

### Deep research before planning

Before entering "plan mode," it helps to have Claude do deep research
first — reading relevant files, understanding dependencies, and writing
findings to a markdown file. This front-loaded context leads to better
plans and fewer mid- execution surprises.

### Voice-driven development works (mostly)

Dictating instructions via Whisper and having Claude Code execute them
is a viable workflow. It forces you to think at a higher level of
abstraction, which often produces cleaner designs. The main friction is
in precise technical terms — variable names, file paths, and code syntax
are harder to dictate than to type.

---

## About

This project is by
[Martijn Hollestelle](https://www.linkedin.com/in/martijn-hollestelle/).
The code is on [GitHub](https://github.com/mlhollestelle/aibm).

**Disclaimer:** This project was developed while I had limited ability
to use a keyboard. Nearly all code was written by AI. It contains
shortcuts and limitations I would not have chosen under normal
circumstances. The purpose is a proof of concept, not an ideal
implementation.
