# The paddle saddle: a behavioural audit

*Step 1 of the Pickleball Bottleneck project. This is the design rationale for
the arrival and patience model in `analysis/simulate_courts.py`. Every claim
below is a hypothesis, and every hypothesis is tied to a named parameter, so a
reader who disagrees with the psychology can change one number and re-run the
project rather than argue with the conclusion.*

---

## The object

A **paddle saddle** (or stack, or rack) is a slotted board at the gate of a
public court. You put your paddle in the next free slot; when a court opens,
the front four paddles play. That is the whole protocol. It is unusual among
queueing systems in three ways, and all three matter.

**It is a physical queue for an intangible good.** You are not waiting for a
court. You are waiting for *three other people plus a court*, and the analysis
found the consequence the hard way: at very low occupancy the wait goes back
**up** — a mean of 11.1 minutes in the emptiest hours against 1.8 minutes at
the sweet spot of about 13 arrivals — because there is nobody to play with.
Open play has a minimum viable crowd as well as a maximum one.

**It is legible only on site.** The single fact that determines whether the
trip is worth making — how deep is the stack — is visible from exactly one
place: the gate. Every decision to leave the house is therefore made under
ambiguity, and ambiguity has a known behavioural signature: people fall back
on habit. Habit says *after work*, so everybody arrives at once.

**It is socially enforced, not staffed.** No host, no clock, no reservation.
The rules are whatever the regulars say they are, which is why the rotation
rule varies from park to park and why changing it costs nothing.

## Four mechanisms, and what each one is worth

**1. Social proof makes crowding self-reinforcing.** A full rack is not only a
cost signal, it is a quality signal: this is where the good games are. So
demand does not spread itself out as congestion rises — the crowd is part of
the draw. This is why *information alone* was expected to move so little, and
the scenario run bears that out: shifting 15% of peak arrivals to the quietest
nearby slot moves the mean peak wait by **0.3 minutes**, about 3%.

*Encoded as:* nothing. This is the assumption I deliberately did **not** make —
arrivals in the simulator are indifferent to how busy the court already is. That
makes the demand-shift result an *optimistic* bound. If social proof is real,
15% adoption buys even less than 3%.

**2. The friction of transition is the real cost, and it is paid twice.**
Getting to a court is a chain of small transitions — change, drive, park, walk,
find the stack. Behavioural work on friction is consistent that these costs are
weighted far above their objective size. The chain is paid on the way in, and
paid again in reverse if you leave without playing. That asymmetry is why
"never got a game" is a much worse outcome than "waited 20 minutes", and why
this project reports the two separately rather than collapsing them into an
average wait.

*Encoded as:* `session_minutes_mean = 85`. A visit is a **duration**, not a
game count. Waiting does not extend your evening; it eats it. Mean games per
visit falls out at 4.67.

**3. Uncertain waiting produces fatigue faster than long waiting.** The
best-established result in queue psychology — Maister's account of waiting
lines, and the operational-transparency work that followed it — is that
unoccupied, unexplained and *open-ended* waits feel far longer than known,
finite ones. A stack gives you no estimate. You cannot tell a 10-minute wait
from a 40-minute one by looking, so you are managing an unbounded downside the
entire time.

*Encoded as:* `patience_first_game_median_min = 28`, lognormal. This is the
single most consequential assumption in the project, and it is the mechanism
behind the finding I did not expect: **congestion does not show up as a long
line, because the line dissolves.** At the busiest hours the mean wait rises
about 9× above the sweet spot, but the share of arrivals who go home without a
game rises about **52×**. The queue is self-limiting. Anyone measuring
congestion by looking at the rack is measuring the survivors.

**4. Commitment flips once you have played.** After a first game the calculus
inverts: the transition cost is sunk, you have been absorbed into the social
unit, and the next wait is spent among people you now know. Waiting becomes
occupied time.

*Encoded as:* `patience_multiplier_after_first_game = 2.2`. This is what makes
the first game the retention event. It also means the population that leaves is
overwhelmingly first-timers and newcomers — precisely the people a parks
department is trying to attract.

## The decision the player cannot currently make

Rationally, a player leaving the house at 17:30 wants to know the state of the
stack at 18:00. They have access to none of it. What they have instead is the
weather, the day of the week, and a memory of last Tuesday.

That gap is the product opportunity, and the analysis sizes it honestly: a
model that sees only what is knowable two hours ahead can steer a player to the
best slot within ±2 hours and cut the expected wait from **7.3 to 4.1
minutes**, capturing about 69% of what perfect hindsight would have delivered.

But the more valuable result is the one this audit predicts and the data
confirms: the advice is worth more for the *games you get* than the minutes you
save. Following it drops the chance of going home without playing from **17.5%
to 8.9%**, and adding a single guardrail — never recommend a slot with less
than 90 minutes of daylight left — takes it to **5.0%**. Mechanism 2 says that
is the number that matters, and it is not the number a wait-time app would
naturally optimise.

---

**What would falsify this.** Instrument one real paddle stack with a camera and
a clock for a season. Three of these four claims are directly measurable:
whether abandonment rises faster than wait (mechanism 3), whether abandonment
concentrates in first-time visitors (mechanism 4), and whether arrivals rise or
fall with observed crowding (mechanism 1). The fourth — that transition cost is
weighted above its objective size — needs a survey. None of this project's
recommendations survive if mechanism 3 is wrong, because the entire argument
for measuring abandonment instead of queue length rests on it.
