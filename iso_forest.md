## Isolation Forest — Full Breakdown

### What is it?

Isolation Forest is an **anomaly detection algorithm** — its job is to find data points that are "weird" compared to the rest.

Unlike most anomaly detectors that first learn what "normal" looks like and then flag deviations, Isolation Forest takes the opposite approach: **directly isolate anomalies** instead of profiling normal points.

---

### Core Intuition

Think about it this way — if you have a forest of decision trees randomly splitting data,  **anomalies get isolated faster** .

Why? Because anomalous points are:

* **Few** — rare in the dataset
* **Different** — far from the dense cluster of normal points

So when you randomly pick a feature and randomly pick a split value, a weird point gets cut off from everything else in very few splits. A normal point buried deep in a cluster needs many splits before it's isolated.

**Isolation Path Length = proxy for anomaly score**

* Short path → isolated quickly → **anomaly**
* Long path → hard to isolate → **normal**

---

### How it Actually Works

**Step 1 — Build iTrees (Isolation Trees)**

* Randomly subsample your data (e.g. 256 points)
* Pick a random feature (e.g. sleep_hours)
* Pick a random split value between min and max of that feature
* Recurse on both sides until each point is alone or max depth hit
* Repeat N times (e.g. 100 trees)

**Step 2 — Compute Anomaly Score**
For each data point, average the path length across all trees.

Normalize it:

```
score = 2^(-avg_path_length / c(n))
```

where `c(n)` is the expected path length for a dataset of size n (normalization constant).

Score interpretation:

* `~1.0` → almost certainly anomaly
* `~0.5` → normal
* `< 0.5` → very normal

**Step 3 — Threshold**
Set `contamination` param (e.g. 0.1 = expect 10% anomalies). sklearn uses this to set the decision boundary and returns `-1` (anomaly) or `1` (normal).

---

### In Your health_analyzer.py Context

Your CSV columns: `sleep_hours, stress_level, energy, mood, steps`

A day gets flagged anomalous if the **combination** of those features is unusual — not just one metric individually. That's important.

Examples of what it catches:

* Slept 7hrs but stress=9, energy=2, mood=1 — pattern inconsistency
* Steps=15000 but sleep=3, energy=1 — physically active but clearly crashed
* Everything normal except mood=1 — could still get flagged if mood is always 7-9

The model sees the  **multivariate pattern** , not just single-column outliers.

---

### Why Isolation Forest specifically?

| Option                     | Why not                                                    |
| -------------------------- | ---------------------------------------------------------- |
| Z-score / IQR              | Univariate only — misses cross-feature patterns           |
| DBSCAN                     | Needs distance metric tuning, bad on mixed-scale features  |
| One-Class SVM              | Slow, kernel tuning needed, overkill for 7-row weekly CSVs |
| Autoencoder                | Way too heavy — you have maybe 30 rows of health data     |
| LOF (Local Outlier Factor) | Good alternative, but slower and needs k-tuning            |

**Isolation Forest wins here because:**

1. Works well on **small datasets** — your weekly CSVs are tiny (7 rows)
2. **No distance/density assumptions** — doesn't care about feature scale relationships
3. Fast — O(n log n)
4. Handles **multivariate anomalies** naturally
5. Single meaningful hyperparameter (`contamination`) which maps directly to your domain knowledge ("I expect ~1 bad day a week")
6. sklearn one-liner — low implementation overhead for a feature that's auxiliary to your core pipeline

---

### The One Weakness to Know

With only 7 data points (one week), the model is working with almost no statistical power. Isolation Forest really shines at 1000+ points. At 7 rows, it's essentially doing **structured heuristics** more than real ML.

The practical fix (which you may already have or should consider): **accumulate weeks** — train the forest on all historical CSVs combined, not just the current week. That way anomaly detection gets genuinely meaningful over time.

elaborate this point that
zscore is univariate and the iso forest is multi?
how like practically is there some n dimensional space the outlirs are detected from or like a tree with many features

**01:39**

Yeah exactly — n-dimensional space is the right mental model.

---

### Z-score (Univariate)

Z-score works on  **one column at a time** :

```
z = (x - mean) / std
```

So for sleep_hours, it computes: is *this sleep value* far from the average sleep value? Flags it if |z| > 2 or 3.

It does this  **independently per column** . It has zero awareness that the columns exist simultaneously for the same day.

So this day:

```
sleep=7, stress=9, energy=2, mood=1, steps=400
```

Z-score checks sleep alone → 7hrs is fine, no flag. Then stress alone → 9 might flag. Then energy → 2 might flag.

It never asks: **"is this specific combination weird?"**

---

### Isolation Forest (Multivariate)

Each day is a **point in 5D space** — one axis per feature.

```
day = (sleep=7, stress=9, energy=2, mood=1, steps=400)
```

This is literally a coordinate: `(7, 9, 2, 1, 400)` plotted in 5-dimensional space.

Your whole week is 7 such points floating in that space. Normal days cluster together — similar sleep, similar stress, correlated energy/mood. An anomalous day sits **far from that cluster** in the combined space, even if no single axis looks extreme.

The classic example:

```
Day A: sleep=4, stress=8   ← low sleep + high stress, consistent, maybe normal for this person
Day B: sleep=8, stress=8   ← good sleep but high stress = weird combination
```

Z-score on stress: both flag or neither flags — same stress value.
Isolation Forest: Day B sits in an **empty region** of the (sleep, stress) 2D plane because that combination rarely occurs. Gets isolated in fewer splits → anomaly.

---

### How the Tree Uses Multiple Features

At each node, the tree picks:

* a **random feature** (e.g. energy)
* a **random split value** within its range

So as you go down the tree, successive splits are cutting across  **different dimensions** . The path to isolation is inherently multi-dimensional — it's not splitting one feature 10 times, it's jumping across features randomly.

A normal point buried in the dense cluster needs many such cuts across many dimensions before it's alone. An outlier in sparse 5D space gets cornered fast regardless of which dimension you cut.

That's the core reason it's multivariate — the  **isolation path traverses the joint feature space** , not each column independently.
