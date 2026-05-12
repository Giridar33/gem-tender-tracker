# Data Cleaning Decisions

This document records every transformation applied in `src/cleaning/transform.py`
and the rationale behind each choice.

---

## 1. Deduplication

**What:** Drop exact duplicates first, then deduplicate on `bid_number` (keep first).

**Why:** GeM sometimes shows the same bid on multiple pages. `bid_number` is the
natural business key; keeping the first occurrence preserves the earliest-scraped data.

---

## 2. Text Normalisation

**What:** Strip leading/trailing whitespace and convert to lowercase for
`title`, `department`, `location`, and `bid_number`.

**Why:** Prevents false duplicates from case differences ("Delhi" vs "delhi").
Lowercase is the standard for text indexing and case-insensitive search.

**Trade-off:** Display values will be lowercase. The API can capitalise on the
frontend if required.

---

## 3. Date Parsing

**What:** Use `python-dateutil` with `dayfirst=True` to parse heterogeneous
date strings into UTC-aware `pandas.Timestamp` objects (ISO 8601).

**Why:** GeM uses DD/MM/YYYY in most places, but some fields use written dates
(e.g. "June 01, 2024"). `dateutil` handles both. `dayfirst=True` matches the
Indian date convention.

**On failure:** Return `None` and log a debug message — the row is still kept.

---

## 4. Currency Parsing (`estimated_value`)

**What:** Strip `₹`, commas, and whitespace; recognise shorthand suffixes
(`L` = lakh = 1e5, `Cr` = crore = 1e7); convert to `float` (INR).

**Why:** GeM displays values in multiple formats (e.g., "₹5,00,000", "2.5L",
"1Cr"). A raw string is not queryable; a float enables range filters in the API.

**On failure:** Return `None`. Rows with no value are kept — the bid is still valid.

---

## 5. Quantity Parsing

**What:** Extract the first numeric token from the raw string using regex.
Units (Nos, Kg, Ltrs) are discarded.

**Why:** Units are inconsistent across categories. Storing a bare number allows
sorting and range filtering. The raw string is not retained because the column
would be redundant.

**Limitation:** Multi-unit bids (e.g., "50 Kg + 10 Ltrs") capture only the
first number. Acceptable for MVP.

---

## 6. Dropping Rows

**What:** Drop rows where `bid_number` is null after all transformations.

**Why:** A row with no identifier cannot be upserted (the conflict target is
`bid_number`) and cannot be linked back to the source. Logging ensures
visibility.

---

## 7. Metadata Column

**What:** Add `scraped_at` (UTC timestamp of when the pipeline ran).

**Why:** Allows staleness detection ("this record hasn't been refreshed in X days")
and is required by the assignment spec (`last_updated_at` on every row).
