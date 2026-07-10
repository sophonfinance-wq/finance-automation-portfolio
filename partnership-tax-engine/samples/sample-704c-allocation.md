# Sample — §704(c) Traditional-Method Allocation (FICTIONAL)

> 🔒 Invented partnership, partners, and amounts for demonstration. Illustrates the public
> IRC §704(c) *traditional method* with the *ceiling rule* — structure and lineage only, not
> real methodology or figures. All USD.

**Partnership:** Sample Harbor LP (fictional) · **Partners:** Atlas LLC (contributes property,
50%) and Beacon LLC (contributes cash, 50%)

---

## Step 0 — Formation: two capital accounts per partner

Atlas contributes a depreciable building; Beacon contributes cash. Book capital is credited at
**fair market value**; tax capital at **carryover tax basis**.

| Partner | Contributes | §704(b) book capital (FMV) | Tax capital (basis) | Built-in gain/(loss) |
|---------|-------------|---------------------------:|--------------------:|---------------------:|
| Atlas LLC | Building | 900,000 | 300,000 | **600,000 (BIG)** |
| Beacon LLC | Cash | 900,000 | 900,000 | 0 |

The **book−tax disparity** Atlas carries (600,000) *is* the §704(c) layer. §704(c) governs how
the partnership's *tax* items are allocated so this disparity is taken into account.

## Step 1 — Annual depreciation: book vs. tax differ

The building has a longer **book** life than its remaining **tax** life — the classic setup:

| Item | Basis | Life | Annual amount |
|------|------:|-----:|--------------:|
| Book depreciation | 900,000 (FMV) | 6 yrs | **150,000 / yr** |
| Tax depreciation | 300,000 (basis) | 3 yrs | **100,000 / yr** |

## Step 2 — Allocate BOOK items by interest % (50/50)

| Partner | Book depreciation share |
|---------|------------------------:|
| Atlas LLC | 75,000 |
| Beacon LLC | 75,000 |

## Step 3 — Allocate TAX depreciation under the traditional method

Tax depreciation goes **first to the non-contributing partner** (Beacon), up to its book share,
to *cure* the disparity. The contributing partner (Atlas) takes the remainder.

| Partner | Target (book share) | Tax depreciation allocated | Note |
|---------|--------------------:|---------------------------:|------|
| Beacon LLC | 75,000 | **75,000** | cured: gets its full book share |
| Atlas LLC | 75,000 | **25,000** | remainder of the 100,000 actual tax dep |
| **Total** | | **100,000** | = actual tax depreciation available |

The §704(c) layer falls by `book dep − tax dep = 150,000 − 100,000 = 50,000` this year
(600,000 → 550,000).

## Step 4 — The CEILING RULE (a different year / harsher fact pattern)

Now suppose the building had only **150,000** of tax basis over a 3-year tax life, so actual
tax depreciation is just **50,000 / yr** — *less* than Beacon's 75,000 book share:

| Partner | Target (book share) | Tax depreciation allocated | Note |
|---------|--------------------:|---------------------------:|------|
| Beacon LLC | 75,000 | **50,000** | ⚑ **capped** — only 50,000 of tax dep exists |
| Atlas LLC | 75,000 | **0** | contributor gets nothing |
| **Total** | | **50,000** | total allocated == actual tax item (ceiling) |

The **ceiling rule** caps total tax depreciation allocated at the 50,000 actually available.
Beacon is short **25,000** of the cure it was entitled to. Under the **traditional method this
distortion is left in place** — the remedial/curative methods that would fix it are *not*
modelled (by design).

## Step 5 — On sale: remaining built-in gain → the contributor

Back to the Step 0–3 facts. After one year the layer has cured by 50,000 (600,000 → **550,000
remaining**), the building's book basis is 750,000 and its tax basis is 200,000. Now sell for
**1,300,000**:

| Measure | Amount | Allocation |
|---------|-------:|------------|
| Book gain = price − book basis (750,000) | 550,000 | 275,000 / 275,000 (by %) |
| Tax gain = price − tax basis (200,000) | 1,100,000 | **Atlas 825,000**, Beacon 275,000 |

The **remaining §704(c) layer of 550,000** is allocated for tax entirely to Atlas (the
contributor) first; the residual tax gain of 550,000 is then split 50/50. So Atlas reports
`550,000 + 275,000 = 825,000` and Beacon `275,000`. The contributing partner is taxed on the
built-in gain it brought in — exactly what §704(c) is for. (Had the tax gain been smaller than
the remaining layer, the **ceiling rule** would again cap Atlas's catch-up at the actual tax
gain available.)

---

**Lineage shown here:** `Contribution (book @ FMV, tax @ basis) → BIG = FMV − basis →
book items by % → tax items: non-contributor first (ceiling-capped) → layer roll-forward →
on-sale catch-up to the contributor`. Every tax allocation is bounded by the **actual tax item
available** (the ceiling rule); the traditional method surfaces — but does not cure — the
resulting distortion.
