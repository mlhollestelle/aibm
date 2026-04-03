# What Happens When You Replace Transport Models With LLMs

AIBM is an experiment in agent-based travel demand modelling where every
behavioural choice — scheduling, destination, mode — is made by an LLM
prompt rather than a statistical model. It covers Walcheren, a peninsula
in Zeeland, the Netherlands, using only open data.

This is a proof of concept, not a production system. The results are messy,
revealing, and — I think — genuinely interesting for anyone thinking about
where AI meets planning.

[Read the full paper →](paper.html)

## Mode share by scenario

![Mode share across LLM scenarios](./figures/mode_shares.png)

## Trip distance distribution

![Trip distance distributions by mode and scenario](./figures/trip_lengths.png)

## Trips per person

![Number of trips per person by scenario](./figures/trips_per_person.png)

---

This project is by [Martijn Hollestelle](https://www.linkedin.com/in/martijn-hollestelle/).
The code is on [GitHub](https://github.com/mlhollestelle/aibm).

**Disclaimer:** This project was developed while I had limited ability to use
a keyboard. Nearly all code was written by AI. It contains shortcuts and
limitations I would not have chosen under normal circumstances.
