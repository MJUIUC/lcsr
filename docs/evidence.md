# Evidence review

Gathered 2026-09-01. Every claim below is tagged with how well I could verify it:

- **[primary]**: read the paper/meta-analysis or its abstract directly.
- **[secondary]**: from a review, wiki, or search summary; not read at source.
- **[inference]**: my reasoning from the above, not a finding.

The point of this document is to be *falsifiable*. If a claim here is wrong, the
design in `design.md` should change.

---

## 1. Spacing works, and there is an optimal gap

**[primary]** Cepeda, Pashler, Vul, Wixted & Rohrer (2006), *Psychological
Bulletin*, meta-analysis of 839 assessments of distributed practice across 317
experiments in 184 articles. Distributed practice beats massed practice robustly.

**[primary]** Cepeda et al. (2008), *Psychological Science* 19(11), 1095-1102,
"Spacing Effects in Learning: A Temporal Ridgeline of Optimal Retention". The
inter-study interval and the retention interval interact. Retention as a function
of gap is an **inverted U**: increasing the gap helps, then hurts. The optimal gap
is roughly **20% of the target test delay** at delays of a few weeks, falling to
about **5-10%** at a one-year delay.

**[secondary]** Expanding intervals outperformed uniform intervals.

> **Design consequence.** If you have an interview on a known date, that date *is*
> the retention interval, and it should drive the schedule. A scheduler that
> ignores your target date is leaving the single best-quantified result in this
> literature on the table. See "Target-date mode" in the design.

---

## 2. Forgetting is loss of access, not loss of storage, and difficulty is the point

**[primary]** Bjork & Bjork (1992), *New Theory of Disuse*. Two strengths:

- **Storage strength**: how well entrenched an item is. Never decreases.
- **Retrieval strength**: how accessible it is *right now*. Decays.

Only retrieval strength shows up in performance; only storage strength is
learning. Critically: **the lower the retrieval strength at the moment of a
successful retrieval, the larger the gain in storage strength.**

**[primary]** Bjork's "desirable difficulties": spacing, interleaving, and
retrieval practice all make practice feel worse and learning end up better.

> **Design consequence.** Reviewing early is close to wasted work, and the
> subjective feeling that a session went badly is not evidence that it did. Any
> feature that makes sessions feel good at the cost of difficulty (streaks,
> easy-mode, self-rating inflation) is actively harmful here.

---

## 3. Retrieval practice is strong for facts, and *does not clearly transfer to problem solving*

This is the most important finding for this project, and it cuts against the
obvious design.

**[primary]** "Retrieval practice may not benefit mathematical word-problem
solving" (PMC9987560). **Three experiments.** Retrieval practice (example–problem
pairs, incomplete examples) was compared against restudying worked examples,
varying initial test difficulty, material similarity, and feedback timing.
Result: **null across all three**. Example–problem pairs did not beat pure
restudy on delayed tests under any manipulation. The authors conclude retrieval
practice may simply not apply to procedural knowledge, which is more
working-memory- and structure-bound than declarative knowledge.

**[secondary]** The broader picture is *mixed*, not uniformly negative:
interleaved practice improves problem-solving in undergraduate physics, and
distributed homework benefits retention and transfer of physics knowledge.
Retrieval practice is more likely to transfer when learners **get feedback** and
when they must genuinely retrieve rather than recognise.

**[secondary]** Carpenter, Pan & Butler (2022), *Nature Reviews Psychology*,
"The science of effective learning with spacing and retrieval practice", the
current authoritative overview. **I could not read the full text (paywalled), so
I am making no specific numerical claims from it.** It belongs on the reading
list before implementation.

> **Design consequence, and it is a big one.** "Re-solve the same LeetCode problem
> on an Anki schedule" is the design with the *weakest* evidential support. It is
> retrieval practice over procedural material, precisely the case that failed to
> replicate, and it optimises recall of one specific solution, which is the
> known failure mode ("I memorised the solution and still bombed the interview").

---

## 4. What *does* have good evidence for problem solving

### 4a. Interleaving, via discriminative contrast

**[primary]** Rohrer & Taylor (2007, 2010); Rohrer, Dedrick & Stershic (2015),
*Journal of Educational Psychology*. Mixing problem *kinds* within an assignment
beats blocking them. The mechanism is the **discriminative-contrast hypothesis**:
interleaving forces you to *choose a strategy on the basis of the problem*, which
blocked practice never requires, under blocking you already know which method to
use because the header of the exercise set told you.

**[primary]** The error analysis is the killer detail: in the blocked condition,
**most test errors were strategy-selection errors**: picking a method belonging
to one of the *other* problem types. That did not happen under interleaving.

**[inference]** This is exactly the LeetCode failure mode. In an interview nobody
says "this is a monotonic stack problem". The skill under test is *pattern
selection under uncertainty*, and blocked practice trains everything except that.

### 4b. Varied practice builds general schemas

**[primary]** Schmidt & Bjork (1992), "New Conceptualizations of Practice";
Schmidt's schema theory. Varied practice beats constant practice for schema
construction, and the benefit shows up specifically on **novel** items rather
than previously-encountered ones. More variability slows initial learning and
produces more general, more robust performance.

> **Design consequence.** The repetition should be of the *pattern*, instantiated
> by a **different problem each time**. Re-solving the identical problem is
> constant practice, the condition that loses.

### 4c. Worked examples beat flailing, for novices

**[primary]** Sweller's worked-example effect: novices given worked examples to
study outperform novices made to solve the equivalent problems. Unguided problem
solving pushes novices into means–ends analysis, which consumes working memory on
extraneous load and leaves nothing for schema construction. Worked examples carry
the same information at lower load.

**[primary]** Kalyuga's **expertise reversal effect**: the same worked examples
that help novices *slow down* learners who already know the material, as the
explanations become redundant.

> **Design consequence.** A failed attempt should route you to a worked solution,
> not to "try harder". And that support must **fade as your stability on that
> pattern grows**: otherwise it flips from helpful to harmful.

### 4d. Successive relearning

**[primary]** Rawson & Dunlosky (2022), *Current Directions in Psychological
Science*. Retrieval to a **correctness criterion**, repeated across **spaced**
sessions. Boosted mastery across a dozen-plus studies (vocabulary, psychology and
statistics terminology, probability concepts). **[secondary]** Roughly three
relearning sessions appear to capture most of the benefit.

> **Design consequence.** "Due today" should mean *retrieve until correct once*,
> not "look at it once and move on".

---

## 5. Which scheduler: FSRS, not SM-2

**[primary]** The open FSRS benchmark (expertium.github.io/Benchmark.html):
16 algorithms, FSRS v3–v6, HLR, Ebisu v2, DASH, ACT-R, GRU/LSTM/RWKV, SM-2, and
an average baseline, over **~727 million reviews from ~10,000 users** (~350M
after filtering). FSRS-6 beats Anki's SM-2 on log loss for **99.6%** of
collections. **[secondary]** roughly 20-30% fewer reviews for equal retention.

**Stated caveats, which matter:**
- SM-2 was never designed to emit probabilities, so converting it into a
  probabilistic predictor required assumptions, the comparison is not fully fair.
- SuperMemo's current proprietary algorithms could not be benchmarked.
- Rankings shift with metric and binning choices.
- **[inference]** An RWKV sequence model beat everything, which tells you the
  DSR model is not the ceiling, but it is not shipping in a small CLI.

FSRS models three per-item quantities (**DSR**): Difficulty, Stability,
Retrievability, with power-law decay, and picks the interval where predicted
recall crosses your **desired retention**. SM-2 just multiplies an interval by a
factor. One is a fitted memory model; the other is a heuristic.

**[primary]** `py-fsrs` (open-spaced-repetition/py-fsrs, **MIT**, `pip install fsrs`)
gives `Scheduler`, `Card`, `Rating {Again, Hard, Good, Easy}`, `ReviewLog`, and an
`Optimizer` that fits the 21 parameters **from your own review logs** and computes
your optimal retention. UTC only. Requires **Python 3.10+**.

**Desired retention.** **[primary]** The optimum is defined as the value that
minimises **workload ÷ knowledge**, and is U-shaped: raise it and you review more;
lower it too far and you forget more and pay in relearning. **[secondary]** Often
cited around **0.85-0.90**; py-fsrs defaults to **0.90**. The honest answer is
that it is personal and the optimizer computes it from your data.

---

## 6. The biggest threat to this whole design

**[inference, and I want this on the record]** FSRS's parameters were fit on
**flashcards**: a fixed cue paired with a fixed response. This design deliberately
makes the item a **pattern** retrieved through a **different problem every time**.
That violates FSRS's modelling assumption. The stability of a *schema* under
varied retrieval is not obviously the same process as the stability of a fixed
cue–response pair, and the 727M-review benchmark says nothing about it.

I do not think this sinks the design, the DSR model is generic enough that the
shape is plausible, but it means **the default parameters are an extrapolation,
not a result.**

The mitigation is the thing that makes this project scientific rather than merely
science-flavoured: **log every review and measure the model's calibration on your
own data.** If predicted recall does not match observed recall, you will see it,
and the optimizer refits. See "Calibration" in the design.

---

## Reading list before implementation

- Carpenter, Pan & Butler (2022), *Nature Reviews Psychology*, full text.
- Cepeda et al. (2008), the ridgeline figure, for target-date mode.
- Rohrer, Dedrick & Stershic (2015), the error-analysis tables.
- "A Stochastic Shortest Path Algorithm for Optimizing Spaced Repetition
  Scheduling", the basis of FSRS's optimal-retention computation.

## Sources

- https://www.yorku.ca/ncepeda/publications/CPVWR2006.html
- https://laplab.ucsd.edu/articles/Cepeda%20et%20al%202008_psychsci.pdf
- http://uweb.cas.usf.edu/~drohrer/pdfs/Rohrer_et_al_2015JEdPsych.pdf
- https://link.springer.com/article/10.3758/s13421-019-00918-4
- https://pmc.ncbi.nlm.nih.gov/articles/PMC9987560/
- https://www.nature.com/articles/s44159-022-00089-1
- https://journals.sagepub.com/doi/full/10.1177/09637214221100484
- https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-06/itow-introducing-desirable-difficulties-into-practice-and-instruction-bjork-and-bjork.pdf
- https://link.springer.com/referenceworkentry/10.1007/978-1-4419-1428-6_415
- https://www.sciencedirect.com/science/article/abs/pii/S0361476X1000055X
- https://expertium.github.io/Benchmark.html
- https://github.com/open-spaced-repetition/py-fsrs
- https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-optimal-retention
