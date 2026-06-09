# RESPONSIVE REFACTOR MASTER PROMPT

You are a Senior UI Architect, Senior Frontend Engineer, Senior QA Engineer, and UX Auditor.

Your task is to completely refactor the responsiveness of this project.

Current Project:

- HTML

- CSS

- Bootstrap

- DataTables

- Modals

- Popups

- Alerts

- Sidebar Layout

- Navbar Layout

- Forms

- Tables

- Dashboard

- Reports

- Day Planning

- All modules

## PRIMARY OBJECTIVE

Eliminate ALL screen-specific media query handling from individual module files.

Create ONE centralized responsive system.

The goal is:

- No text cropping

- No button cropping

- No modal overflow

- No table cutoff

- No sidebar overlap

- No navbar overlap

- No popup clipping

- No horizontal scrolling

- No hidden content

- No broken alignments

The UI must work perfectly on:

ResolutionType1920x1080Desktop1680x1050Desktop1600x900Desktop1440x900Desktop1400x1050Desktop1366x768Laptop1360x768Laptop1280x1024Desktop1280x960Desktop1280x800Laptop1280x768Laptop1280x720Small Laptop1152x864Legacy1024x768Tablet Landscape800x600Minimum Supported

---

# TABLET TARGET

Primary tablet:

Samsung Galaxy Tab A9+

Specs:

Resolution:

1920 × 1200

Aspect Ratio:

16:10

Viewport Target:

1024px width class

Base Font:

18px

This tablet is the PRIMARY responsive benchmark.

All tablet screens must render perfectly using:

18px base font.

---

# RESPONSIVE STRATEGY

Create:

```
```
assets/css/responsive.css
```
```

This file becomes:

THE SINGLE SOURCE OF TRUTH

No responsive logic should remain in:

- module css

- page css

- html files

- inline styles

Move everything into:

responsive.css

---

# FONT SYSTEM

Rule:

Smaller screen = Larger font

Larger screen = Smaller font

Apply globally.

### Desktop Large

1920+

16px

### Desktop

1440-1919

15px

### Laptop

1280-1439

16px

### Tablet

1024-1279

18px

### Small Tablet

800-1023

19px

### Minimum

800 and below

20px

Use CSS variables.

Example:

```
```
:root{
--base-font-size:16px;
}
```
```

Never hardcode font sizes.

---

# RESPONSIVE.CSS STRUCTURE

Create sections:

```
```
01 ROOT VARIABLES
02 TYPOGRAPHY
03 SIDEBAR
04 NAVBAR
05 FOOTER
06 TABLES
07 DATATABLES
08 FORMS
09 BUTTONS
10 MODALS
11 ALERTS
12 CARDS
13 DASHBOARD
14 REPORTS
15 DAY PLANNING
16 UTILITIES
17 TABLET
18 MOBILE
```
```

---

# REMOVE ALL MEDIA QUERIES

Search entire project.

Find:

```
```
@media
```
```

inside:

- html

- css

- templates

- module styles

Remove.

Move logic into responsive.css.

Keep only centralized breakpoints.

---

# SIDEBAR RULES

Requirements:

Never crop text.

Allow wrapping.

No ellipsis.

No hidden menu names.

Expanded:

280px

Collapsed:

70px

Must work:

- Desktop

- Laptop

- Tablet

---

# TABLE RULES

All tables:

```
```
table-layout:auto;
```
```

No fixed widths.

Headers:

wrap properly.

Cells:

wrap properly.

No hidden columns.

No cropped text.

DataTables must remain functional.

---

# FORM RULES

Inputs:

100% width

Minimum height:

44px

Tablet:

50px

Dropdowns:

must never overlap.

---

# BUTTON RULES

Minimum:

44px height

Tablet:

50px height

Text always visible.

No button clipping.

No icon clipping.

---

# MODAL RULES

All modals:

Width:

Desktop:

70%

Tablet:

90%

Small:

95%

Height:

Auto

Max height:

90vh

Internal scrolling only.

Never page scrolling.

---

# ALERTS

SweetAlert

Bootstrap Alert

Toast

Custom Popup

All must scale correctly.

No cropped buttons.

No cropped text.

---

# DAY PLANNING MODULE

This is highest priority.

Validate:

- tables

- filters

- action buttons

- sticky columns

- search

- pagination

- modals

- barcode popup

- scan popup

Must work on all resolutions.

No regressions.

---

# TESTING REQUIREMENTS

For EVERY screen:

Test:

1920x1080

1680x1050

1600x900

1440x900

1400x1050

1366x768

1360x768

1280x1024

1280x960

1280x800

1280x768

1280x720

1152x864

1024x768

800x600

For each resolution:

Check:

- overflow

- crop

- clipping

- hidden text

- hidden buttons

- modal fit

- sidebar fit

- navbar fit

- footer fit

- datatable fit

---

# AUTO QA

Before modifying next screen:

Run self-review.

Checklist:

□ No horizontal scrollbar

□ No vertical clipping

□ No overlap

□ No cropped text

□ No cropped buttons

□ No hidden icons

□ No modal overflow

□ No alert overflow

□ No sidebar overflow

□ No navbar overflow

□ No footer overlap

Only proceed if ALL pass.

---

# OUTPUT REQUIRED

For each module:

Provide:

1. Files modified

2. Media queries removed

3. Responsive rules added

4. Issues fixed

5. Screenshots generated

6. QA result

7. Remaining risks

Do NOT skip any screen.

Do NOT assume success.

Verify before reporting success.

---

### Based on the HTML you uploaded, I can already see hundreds of scattered `@media` blocks inside `base.html` itself. A proper fix would be:

1. Extract all responsive rules from `base.html` into `assets/css/responsive.css`.

2. Keep only structure/layout CSS in `base.html`.

3. Use CSS variables for font scaling.

4. Make Samsung Tab A9+ (1920×1200, 16:10) the primary tablet benchmark with **18px base font**.

5. Remove duplicated modal/sidebar responsive code (your file currently contains many repeated media-query sections).