# SCOUT Strategy Reference

This document provides detailed decision guidance for complex situations.
Read this when you face ambiguity during the GATHER phase.

---

## 1. Core Decision Heuristics

### Search vs. Read

| Situation | Action |
|-----------|--------|
| Need to find WHERE information is | Use Grep (cheap) |
| File is small (<30k tokens) | Read entire file |
| File is medium (30k-100k tokens) | Grep → Read(offset, limit) |
| File is very large (>100k tokens) | Grep only; multiple targeted searches |
| Grep returns no results | Try synonym keywords, then broader patterns |
| Grep returns too many results | Narrow with more specific terms |

### When to Use Read with offset/limit

After Grep finds relevant line numbers:
- Set `offset` to ~10 lines before the first match
- Set `limit` to cover the relevant section (typically 30-100 lines)
- Read surrounding context, not just the matching line

### When to Stop Gathering

- All TodoWrite items are marked completed
- You have info for every component of the question
- For comparisons: you have data for ALL sides
- For multiple choice: you have evidence for the correct answer

---

## 2. Anti-Patterns (Critical Failures)

### Invisible Reader
**What**: Reading a file and finding relevant info, but NOT calling `workspace.py append`.
**Why it's fatal**: The evaluator ONLY sees workspace content. Unrecorded info = nonexistent info.
**Rule**: After EVERY Read/Grep that yields relevant data → immediately `workspace.py append`.

### Blind Reader
**What**: Calling Read on a file without first running `workspace.py file-info`.
**Why it's fatal**: May waste huge token budget on a file that should be grep-only.
**Rule**: ALWAYS run file-info before the first Read of any file.

### Premature Guesser
**What**: Answering the question without running the evaluation step.
**Why it's fatal**: Violates the decoupled epistemic state principle. Answer may be incomplete.
**Rule**: MUST evaluate before EVERY final answer. No exceptions.

### Stubborn Reader
**What**: Ignoring `needs_normalization: true` from file-info and proceeding to Read/Grep.
**Why it's fatal**: Long lines cause Grep to return massive unusable chunks.
**Rule**: If needs_normalization → normalize first, then proceed.

### Lazy Planner
**What**: Skipping TodoWrite for complex multi-part questions.
**Why it's fatal**: Leads to scattered, incomplete information gathering.
**Rule**: For questions with 2+ parts or comparison elements → ALWAYS plan with TodoWrite.

---

## 3. Question Classification Decision Tree

### Type A: Fact-Finding (who/what/when/where/how much)

```
1. Identify the key entity/fact to find
2. Generate 2-3 keyword variants
3. Grep all files for keywords
4. Read the matching sections (offset/limit)
5. Record the fact → Evaluate → Answer
```

**Example keywords for "When was the company founded?":**
- "founded", "established", "incorporated"
- "year of establishment", company name + year pattern

### Type B: Comparative Analysis (compare/contrast/difference)

```
1. Split into N independent sub-searches (one per comparison element)
2. For each element: Grep → Read → Record
3. Ensure you have data for ALL elements before evaluation
4. Synthesize comparison in final answer
```

**Critical**: Do NOT evaluate until you have info for ALL comparison elements.

### Type C: Summary/Overview (summarize/describe/explain)

```
1. Locate the target section boundaries (chapter/section markers)
2. Read in chunks (offset/limit), recording key points
3. May need multiple Read passes across the section
4. Record main points, supporting evidence, conclusions
```

### Type D: Multiple Choice

```
1. Identify what each option claims
2. Search for evidence supporting the CORRECT option
3. Search for evidence RULING OUT other options (if possible)
4. Record: correct option evidence + elimination reasoning
5. Evaluate → Answer with option letter + justification
```

**Critical**: Record evidence for WHY other options are wrong, not just why one is right.

---

## 4. Keyword Strategy

### General Rules
- Start with exact phrases likely in the text
- Prepare 2-3 synonym variants
- For CJK documents: consider simplified/traditional variants
- For English: consider case sensitivity, abbreviations, acronyms
- Use regex patterns when exact matches fail: `[0-9]{4}` for years

### Progressive Broadening
1. First try: exact term from the question
2. Second try: synonyms and related terms
3. Third try: broader category terms
4. Fourth try: surrounding context terms (what would appear NEAR the answer)

### Multi-language Awareness
- If document language differs from query language, translate key terms
- Search in BOTH languages when uncertain
- Consider transliteration for names

---

## 5. Workspace Management Best Practices

### Entry Granularity
- One entry per distinct piece of information
- Include enough context to understand without re-reading the file
- Always note the exact source (filename + line numbers)

### Effective Tagging
- Use consistent tag names across entries
- Common tags: topic names, chapter numbers, data types
- Tags enable efficient workspace search later

### When to Use workspace search
- Before searching a document topic, check if already recorded
- Avoid duplicate entries for the same information
- Quick lookup when synthesizing multi-entry answers

---

## 6. Large File Handling Protocol

For files estimated at >100k tokens:

1. **Never attempt full Read**
2. Use Grep with multiple targeted keywords
3. Note line numbers from Grep results
4. Read only narrow windows around matches (limit: 50-100 lines max)
5. If key information spans a wide range, make multiple Read calls
6. Record each chunk immediately — do not accumulate in memory

For files needing normalization:
1. Run normalize ONCE
2. Then proceed with normal Grep → Read flow
3. Do NOT normalize files you won't read
