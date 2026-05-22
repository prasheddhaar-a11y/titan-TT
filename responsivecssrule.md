# Required Responsive Logic Update

Replace existing responsive rules with the following finalized viewport logic.

## Final Responsive Breakpoints

### Mobile

```text
< 768px
```

Fonts:

```text
Body/Table      : 15px
Heading         : 16px
Labels          : 15px
Pagination      : 15px
```

---

### Tablet

Actual tablet devices only.

Example:

```text
Samsung Galaxy Tab A9+ 5G
Approx viewport:
1280 × 800
```

Viewport:

```text
1024px – 1280px
```

Fonts:

```text
Body/Table      : 18px
Heading         : 20px
Labels          : 18px
Pagination      : 18px
Sidebar         : 18px
Submenu         : 18px
```

Important:
Tablet UI must be clearly larger and more readable than desktop.

---

### Desktop / Laptop

Viewport:

```text
1281px – 1919px
```

Fonts:

```text
Body/Table      : 11px
Heading         : 11px
Labels          : 11px
Pagination      : 11px
Sidebar         : 10px
Submenu         : 10px
```

Important:
Desktop must use compact enterprise density UI.

Expected:

* More rows visible
* Reduced spacing
* Compact tables
* Reduced sidebar/submenu size

---

### Wide Desktop

Viewport:

```text
>= 1920px
```

Fonts:

```text
Body/Table      : 13px
Heading         : 13px
Labels          : 13px
Pagination      : 13px
Sidebar         : 12px
Submenu         : 12px
```

---

# Important Technical Requirement

Current issue:
Desktop monitor widths are still activating tablet mode because responsiveness relies only on:

```javascript
window.innerWidth
```

This is incorrect.

Need smarter viewport/device detection using:

```javascript
window.innerWidth
window.innerHeight
screen.width
screen.height
navigator.userAgent
pointer: coarse
touch support
devicePixelRatio
```

Important:
Do NOT blindly apply same viewport logic for all devices.

Example:

```text
1920×1080 desktop monitor
browser viewport reduced to 1276
```

Should STILL behave as:

```text
Desktop compact UI
```

NOT tablet UI.

---

# Mandatory Cleanup

Remove ALL:

* HTML media queries
* inline responsive CSS
* duplicate breakpoints
* conflicting font overrides

Keep responsiveness ONLY in:

```text
ttt-responsive-system.css
ttt-responsive-system.js
```

Ensure:

* responsive CSS block stays LAST in CSS file
* JS breakpoint logic matches CSS exactly

---

# Required Validation

Validate responsiveness simultaneously for:

```text
800×600
1024×768
1152×864
1280×720
1280×800
1280×1024
1366×768
1440×900
1600×900
1680×1050
1920×1080
```

Ensure:

* Tablet and desktop visually look clearly different
* Tablet UI larger/readable
* Desktop UI compact
* Sticky pagination/footer works correctly
* Internal table scrolling works correctly
* Existing functionality remains intact
