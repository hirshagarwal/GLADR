# GBM Recurrence Deck — Style Reference
# Dr. Hirsh Agarwal | QMC Nottingham | v1.0 May 2026

---

## Colours

| Role        | Name        | Hex     | RGB              | When to use                                      |
|-------------|-------------|---------|------------------|--------------------------------------------------|
| Primary     | BCG Green   | #006747 | 0, 103, 71       | Title slides, section headers, close slides      |
| Secondary   | Light Sage  | #E8F5EE | 232, 245, 238    | Content slide backgrounds                        |
| Text dark   | Near-black  | #1A1A1A | 26, 26, 26       | All body text on light backgrounds               |
| Text light  | White       | #FFFFFF | 255, 255, 255    | All text on green backgrounds                    |
| Neutral     | Warm grey   | #6B7280 | 107, 114, 128    | Captions, footnotes, secondary labels            |
| Accent      | Amber       | #F59E0B | 245, 158, 11     | ONE key callout per findings slide — sparingly   |

Rules:
- Never use any colour outside this palette
- Never use gradients
- Amber is reserved for the single most important number per slide
- Never use two accent colours on the same slide
- Background alternation: green (title) → white or sage (content) → green (close)

---

## Typography

| Element              | Font          | Size    | Weight | Colour    |
|----------------------|---------------|---------|--------|-----------|
| Slide headline       | Calibri       | 28–32pt | Bold   | Dark/White|
| Body text            | Calibri       | 16pt    | Regular| 1A1A1A    |
| Large callout number | Calibri       | 60–72pt | Bold   | Amber/White|
| Table headers        | Calibri       | 14pt    | Bold   | White on green|
| Captions/footnotes   | Calibri       | 11pt    | Regular| 6B7280    |
| Section labels       | Calibri       | 12pt    | Bold   | 006747    |

Rules:
- Never underline titles
- Never centre body text — left-align all paragraphs and lists
- Centre only large standalone callout numbers
- Title size must create strong contrast with 16pt body (never reduce headline below 24pt)

---

## Slide structure

### Background logic (sandwich)
- Slides 1, 2 (exec summary): white/sage — exception, light for summary
- Slide 1 (title): GREEN (006747)
- Slides 3–12 (content): WHITE (#FFFFFF) or SAGE (#E8F5EE), alternating
- Slides 13–14 (close): GREEN (006747)

### Headline rule
Every slide headline is a DECLARATIVE CONCLUSION, not a topic label.
  ✓ "Two routinely available variables predict distant recurrence"
  ✗ "Results"
  ✓ "Existing models are too complex for routine clinical use"
  ✗ "Literature review"

### Content density
- Maximum 3 bullet points per content slide
- Each bullet is a complete thought (full sentence or meaningful phrase)
- Every slide must have at least one visual element:
  charts, callout numbers, diagrams, timelines, or structured layouts
- No pure text slides

### Margins and spacing
- Minimum 0.5" margins from slide edges
- 0.3–0.5" between content blocks
- Leave breathing room — never fill every inch

---

## Visual elements

### Large stat callouts
- Number: 60–72pt bold, amber (#F59E0B) on light background 
  or white (#FFFFFF) on green background
- Label below: 14pt regular, grey (#6B7280) or white
- Example: "0.773" large + "Model AUC" below

### Forest plot style (OR display)
- Variable label: left-aligned, 16pt
- OR value: large amber callout
- CI and p-value: 12pt grey below the OR
- Horizontal rule separating rows

### Diagrams and flows
- CONSORT flow: rectangular boxes, green borders, near-black text
- Timeline: green circles at each point, connecting line, labels below
- Management fork: two columns with coloured headers

### Tables
- No heavy borders — use light grey row separators only
- Header row: green background (#006747), white text
- Alternating rows: white / sage (#E8F5EE)
- Never use Excel-style thick black borders

### Callout boxes
- Green callout (#006747 background, white text): for key conclusions
- Amber callout (#F59E0B background, dark text): for single most important stat
- Sage callout (#E8F5EE background, dark text): for neutral information panels

---

## What to avoid (common AI slide mistakes)

- ✗ Decorative full-width coloured bars or ribbons
- ✗ Accent lines under titles
- ✗ Clip art or generic icons used decoratively
- ✗ Cream or beige backgrounds (use white or sage only)
- ✗ Gradient fills of any kind
- ✗ Text overflow beyond box boundaries
- ✗ Centred body text
- ✗ More than one accent colour per slide
- ✗ Repeating the same layout on consecutive slides
- ✗ Topic-label headlines ("Results", "Methods", "Background")
- ✗ Low-contrast text (light grey on white, dark on dark green without white text)

---

## Audience subsets (slide numbers to show)

| Audience                  | Slides                        |
|---------------------------|-------------------------------|
| SBNS oral (5 min)         | 1, 3, 4, 7, 8, 9, 13         |
| New clinical collaborators| All 14                        |
| Quick intro / pitch       | 1, 2, 7, 10, 13               |

---

## Placeholder convention
All numbers in square brackets [N], [X] are placeholders
to be manually populated from the verified Excel backup:
  SBNS_abstract_backup.xlsx

Key numbers to populate:
- Slide 2: Total registry N, AUC value
- Slide 5: Total registry N, intermediate cohort Ns
- Slide 8: TTR columns 1 and 3 (RCE by full cohort, local recurrers)
- Slide 10: Any updated timing data

---

## File naming convention
GBM_Recurrence_Deck_[YYYYMMDD].pptx
Example: GBM_Recurrence_Deck_20260503.pptx

When regenerating after number updates:
GBM_Recurrence_Deck_v2_[YYYYMMDD].pptx
