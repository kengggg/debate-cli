# Mermaid Use Case Diagram Plugin - v1 Specification

## 1. Problem Statement

UML Use Case diagrams are a standard tool for business analysts and architects to map actor-system interactions. Today, teams draw these manually in tools like Miro, producing raster images that:

- Cannot be versioned in git
- Cannot be read or written by coding agents
- Cannot serve as a single source of truth across documentation, code, and collaboration

Mermaid supports flowcharts, sequence diagrams, class diagrams, ER diagrams, and more — but **has no native use case diagram type**. Teams work around this with `flowchart LR` hacks, but the result lacks UML semantics (no stick-figure actors, no ellipse use cases, no left/right placement control).

## 2. Goals

1. **Descriptive syntax** — a text-based DSL for use case diagrams that is readable by both humans and coding agents
2. **Visual fidelity** — rendered output visually comparable to hand-drawn Miro diagrams (stick-figure actors, ellipse use cases, system boundary box, straight-line associations)
3. **Mermaid-native** — implemented as a plugin via `mermaid.registerDiagram()`, zero core modifications, consistent with Mermaid syntax conventions
4. **Scale** — must handle diagrams with up to 30 actors and 30 use cases without layout breakdown
5. **Ground truth** — deterministic rendering (declaration-order layout) so the `.mermaid` file is the authoritative source

## 3. Scope

### In scope (v1)

| Feature | Notes |
|---|---|
| Actor declaration with left/right placement | UML stick figure icon |
| Use case declaration | Ellipse shape |
| Single system boundary | Rectangle with title |
| Association links (line, arrow, auto) | `---`, `--->`, `--` |
| Fan-out shorthand | `AR1 --- UC1 & UC2 & UC3` |
| Per-node and class-based styling | `style`, `classDef`, `class` |
| Actor auto-positioning with manual override | `actorLayout auto\|manual` |
| Unicode text support | Thai, CJK, etc. |
| SVG output | PNG via mermaid-cli (mmdc) |

### Deferred (v2+)

| Feature | Notes |
|---|---|
| `<<include>>` / `<<extend>>` relationships | Dashed arrows between use cases |
| Generalization (inheritance) | Actor-to-actor and UC-to-UC |
| Multiple system boundaries | Side-by-side or stacked |
| Notes / annotations | Attached to use cases |
| Horizontal layout option | `direction LR` |

## 4. Syntax Specification

### 4.1 Diagram Declaration

```mermaid
usecaseDiagram
```

All content is indented below this keyword. Layout is **vertical** (use cases stacked top-to-bottom, actors on left/right sides).

### 4.2 Actor Declaration

```
[left|right] actor <ID> [as "<Label>"]
```

- `left` or `right` controls which side of the system boundary the actor appears on
- **Default side: `left`** (if omitted)
- `ID` is a code-friendly identifier (alphanumeric + underscore)
- `as "<Label>"` is the display name (optional — if omitted, `ID` is used as label)
- Actors render as **UML stick figures** with the label below

Examples:
```mermaid
usecaseDiagram
    actor User                          %% left side, label "User"
    left actor Admin as "System Admin"  %% left side, label "System Admin"
    right actor API as "External API"   %% right side, label "External API"
```

### 4.3 System Boundary

```
system "<System Name>" {
    ...use case declarations...
}
```

- Renders as a **rectangle** with the system name at the **top-left corner**
- Contains all use case declarations
- **v1 supports exactly one `system` block** per diagram
- Use cases declared outside a `system` block are an error in v1

Example:
```mermaid
usecaseDiagram
    system "Investment Budget Transfer" {
        usecase UC1 as "Create Request"
        usecase UC2 as "Approve Request"
    }
```

### 4.4 Use Case Declaration

```
usecase <ID> [as "<Label>"]
```

- Must appear inside a `system` block
- Renders as an **ellipse** with the label centered inside
- Vertical order follows **declaration order** (first declared = topmost)
- `as "<Label>"` is optional — if omitted, `ID` is used as label
- Long labels wrap within the ellipse

Examples:
```mermaid
    usecase UC1 as "Create Budget Request"
    usecase UC2 as "Review and Approve"
    usecase ShortName
```

### 4.5 Relationships

```
<ActorID> <LinkType> <TargetID> [& <TargetID>]*
```

#### Link Types

| Syntax | Name | Rendering | Use When |
|---|---|---|---|
| `---` | Line | Solid line, **no** arrowhead | Standard UML association (most common) |
| `--->` | Arrow | Solid line, **with** arrowhead at target | Directed association (actor initiates) |
| `--` | Auto | Renderer decides (defaults to solid line, no arrowhead) | Let engine optimize |

#### Fan-out Shorthand

Connect one actor to multiple use cases in a single line using `&`:

```mermaid
    AR1 --- UC1 & UC2 & UC3
    %% equivalent to:
    %% AR1 --- UC1
    %% AR1 --- UC2
    %% AR1 --- UC3
```

#### Rules
- Relationships are declared **outside** the `system` block (after closing `}`)
- Both directions are valid: `Actor --- UseCase` or `UseCase --- Actor` (semantically identical for lines)
- For arrows (`--->`), the arrowhead points to the target (right-hand side)
- Self-referencing or actor-to-actor links are **not supported in v1**

### 4.6 Styling

#### Class-based (recommended for reuse)

```mermaid
    classDef highlighted fill:#f5a623,stroke:#e09000,color:#fff
    class UC5,UC7 highlighted
```

#### Per-node style directive

```mermaid
    style UC5 fill:#f5a623,stroke:#e09000
    style Admin stroke:#ff0000,stroke-width:2px
```

#### Supported style properties

| Property | Applies To | Example |
|---|---|---|
| `fill` | Actor icon bg, use case fill, system boundary fill | `fill:#f5a623` |
| `stroke` | Border/outline color | `stroke:#333` |
| `stroke-width` | Border thickness | `stroke-width:2px` |
| `color` | Text color | `color:#fff` |
| `font-size` | Label text size | `font-size:14px` |

### 4.7 Directives

#### Actor Layout

```mermaid
    actorLayout auto     %% default: position actors at midpoint of connected UCs
    actorLayout manual   %% use declaration order for vertical positioning
```

- **`auto`** (default): Each actor is vertically positioned at the midpoint of its connected use cases. Collision avoidance ensures no overlap — when two actors would collide, declaration order breaks ties (earlier = higher).
- **`manual`**: Actors are stacked in declaration order with even spacing, left-side actors independently from right-side actors.

### 4.8 Comments

```mermaid
    %% This is a comment (same as all Mermaid diagrams)
```

## 5. Complete Example

Equivalent to the Miro reference render (`USECASE-EXAMPLE-RENDER.jpg`):

```mermaid
usecaseDiagram
    left actor AL1 as "Actor Left 1"
    right actor AR1 as "Actor Right 1"
    right actor AR2 as "Actor Right 2"
    right actor AR3 as "Actor Right 3"
    right actor AR4 as "Actor Right 4"
    right actor AR5 as "Actor Right 5"

    system "การรับโอนงบลงทุน" {
        usecase UC1 as "Use Case 1"
        usecase UC2 as "Use Case 2"
        usecase UC3 as "Use Case 3"
        usecase UC4 as "Use Case 4"
        usecase UC5 as "Use Case 5"
        usecase UC6 as "Use Case 6"
        usecase UC7 as "Use Case 7"
        usecase UC8 as "Use Case 8"
        usecase UC9 as "Use Case 9"
    }

    AR1 --- UC1 & UC2 & UC3
    AL1 --- UC2 & UC4
    AR2 --- UC4 & UC5
    AR3 --- UC6
    AR4 --- UC7 & UC9
    AR5 --- UC8

    classDef highlighted fill:#f5a623,stroke:#e09000
    class UC5,UC7 highlighted
```

## 6. Rendering Specification

### 6.1 Layout Model

```
    ┌──────────────────────────────────────────────────────┐
    │                    SVG Canvas                         │
    │                                                      │
    │  [Left Actors]   ┌─ System Boundary ─┐  [Right Actors]
    │                  │                    │               │
    │   ○  Actor L1    │   (  Use Case 1 ) │    ○  Actor R1│
    │  /|\             │   (  Use Case 2 ) │   /|\         │
    │  / \             │   (  Use Case 3 ) │   / \         │
    │                  │       ...         │               │
    │   ○  Actor L2    │   (  Use Case N ) │    ○  Actor R2│
    │  /|\             │                    │   /|\         │
    │  / \             └────────────────────┘   / \         │
    │                                                      │
    └──────────────────────────────────────────────────────┘
```

### 6.2 Element Dimensions

| Element | Sizing Rule |
|---|---|
| **Use case ellipse** | Width: `max(textWidth + 40px, 120px)`. Height: `width * 0.55`. All ellipses within a system share the same width (widest wins) for visual alignment. |
| **Stick figure** | Fixed: `30w x 50h` px. Label below, centered, max-width 100px with word-wrap. |
| **System boundary** | Width: `ellipseWidth + 80px` (40px padding each side). Height: `sum(ellipseHeights) + (N-1) * verticalGap + 60px` (30px top/bottom padding). |
| **Vertical gap** | Between use cases: `20px` default. |
| **Horizontal gap** | Between actor column and system boundary: `60px`. |

### 6.3 Actor Positioning Algorithm

**When `actorLayout auto` (default):**

1. For each actor, compute `midY` = average of the Y-centers of all connected use cases
2. Sort actors on each side by `midY` (ascending = top to bottom)
3. For actors with identical `midY`, sort by declaration order
4. Walk the sorted list top-to-bottom; if an actor's computed Y would place it within `minGap` (60px) of the previous actor, push it down to `previousY + minGap`
5. Left-side and right-side actors are positioned independently

**When `actorLayout manual`:**

1. Left-side actors stack top-to-bottom in declaration order
2. Right-side actors stack top-to-bottom in declaration order
3. First actor on each side aligns with the top of the system boundary
4. Spacing: `max(60px, systemHeight / actorCount)`

### 6.4 Line Routing

- **Straight lines** from actor icon center to the nearest point on the use case ellipse edge
- Lines pass **through** the system boundary border (no routing around it)
- No curve or elbow routing in v1
- When multiple lines from one actor fan out to multiple use cases, each line is independent (no shared segments or junction points)

### 6.5 Line Crossing Minimization

At 30x30 scale, line crossings are inevitable. Mitigation strategies:

1. **Declaration order is primary** — users control layout by ordering their declarations sensibly (related actors near related use cases)
2. **Auto actor positioning** — places actors near their connected use cases, naturally reducing crossings
3. **Future v2** — optional `optimize` directive for algorithmic crossing reduction

### 6.6 Stick Figure SVG

The UML stick figure actor icon as an SVG path:

```svg
<!-- Head -->
<circle cx="15" cy="8" r="8" fill="none" stroke="#333" stroke-width="1.5"/>
<!-- Body -->
<line x1="15" y1="16" x2="15" y2="34" stroke="#333" stroke-width="1.5"/>
<!-- Arms -->
<line x1="0" y1="24" x2="30" y2="24" stroke="#333" stroke-width="1.5"/>
<!-- Left leg -->
<line x1="15" y1="34" x2="3" y2="50" stroke="#333" stroke-width="1.5"/>
<!-- Right leg -->
<line x1="15" y1="34" x2="27" y2="50" stroke="#333" stroke-width="1.5"/>
```

### 6.7 Typography

- Font: inherit from Mermaid theme (default: `"trebuchet ms", verdana, arial, sans-serif`)
- Use case label: centered within ellipse, word-wrap if exceeding ellipse width minus padding
- Actor label: centered below stick figure, word-wrap at 100px max-width
- System name: top-left corner of boundary rectangle, 14px bold
- **Full Unicode support** — Thai, CJK, Cyrillic, etc.

### 6.8 Default Color Palette

| Element | Fill | Stroke | Text |
|---|---|---|---|
| Use case ellipse | `#ffffff` | `#333333` | `#333333` |
| System boundary | `#ffffff` | `#999999` | `#333333` |
| Stick figure | n/a | `#333333` | `#333333` |
| Association line | n/a | `#333333` | n/a |

These defaults are overridable via Mermaid theming and per-node styling.

## 7. Plugin Architecture

### 7.1 Package Structure

```
mermaid-usecase-diagram/
  src/
    index.ts              # Plugin entry point, exports diagram definition
    detector.ts           # Regex detector for 'usecaseDiagram'
    parser.ts             # Text → data model
    usecaseDiagramDb.ts   # Data store (actors, use cases, system, relationships)
    renderer.ts           # Data model → SVG (using D3)
    styles.ts             # Default CSS
    types.ts              # TypeScript interfaces
  examples/
    ...
  tests/
    parser.test.ts
    renderer.test.ts
  package.json
  tsconfig.json
```

### 7.2 Registration API

```typescript
// Consumer usage:
import mermaid from 'mermaid';
import usecaseDiagram from 'mermaid-usecase-diagram';

mermaid.registerDiagram('usecaseDiagram', usecaseDiagram);

// Then in HTML/Markdown:
// ```mermaid
// usecaseDiagram
//     ...
// ```
```

### 7.3 Data Model (TypeScript interfaces)

```typescript
type Side = 'left' | 'right';
type LinkType = 'line' | 'arrow' | 'auto';
type ActorLayoutMode = 'auto' | 'manual';

interface Actor {
  id: string;
  label: string;
  side: Side;
  // Resolved during rendering:
  x?: number;
  y?: number;
}

interface UseCase {
  id: string;
  label: string;
  // Order is preserved from declaration
  order: number;
  // Resolved during rendering:
  x?: number;
  y?: number;
  width?: number;
  height?: number;
}

interface SystemBoundary {
  name: string;
  useCases: UseCase[];
}

interface Relationship {
  from: string;       // Actor or UseCase ID
  to: string;         // Actor or UseCase ID
  linkType: LinkType;
}

interface StyleClass {
  name: string;
  properties: Record<string, string>;
}

interface NodeStyle {
  nodeId: string;
  properties: Record<string, string>;
}

interface UseCaseDiagramDb {
  actors: Actor[];
  system: SystemBoundary;
  relationships: Relationship[];
  styleClasses: StyleClass[];
  nodeStyles: NodeStyle[];
  actorLayout: ActorLayoutMode;

  // Parser populates, renderer reads
  addActor(id: string, label: string, side: Side): void;
  addUseCase(id: string, label: string): void;
  setSystem(name: string): void;
  addRelationship(from: string, to: string, linkType: LinkType): void;
  addStyleClass(name: string, props: Record<string, string>): void;
  applyClass(nodeIds: string[], className: string): void;
  addNodeStyle(nodeId: string, props: Record<string, string>): void;
  setActorLayout(mode: ActorLayoutMode): void;
}
```

### 7.4 Parser Strategy

Hand-written **recursive descent parser** for v1 (simplest, no external dependency). Line-by-line parsing:

1. Detect `usecaseDiagram` keyword → begin parsing
2. For each subsequent line (trimmed, skip empty/comments):
   - Match against patterns in priority order:
     - `actorLayout (auto|manual)`
     - `(left|right)? actor <ID> (as "<Label>")?`
     - `system "<Name>" {`
     - `}` (close system block)
     - `usecase <ID> (as "<Label>")?`
     - `classDef <Name> <props>`
     - `class <IDs> <className>`
     - `style <ID> <props>`
     - `<ID> (---|---\>|--) <ID> (& <ID>)*` (relationship)
3. Populate the `UseCaseDiagramDb`

Migrate to Langium grammar if/when contributing to mermaid-js upstream.

### 7.5 Renderer Pipeline

```
UseCaseDiagramDb
      │
      ▼
  ┌─────────────────┐
  │  1. Measure      │  Calculate text widths, ellipse sizes
  │     text         │  (using D3 + invisible SVG text elements)
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │  2. Layout       │  Position use cases (declaration order),
  │     compute      │  system boundary, actors (auto/manual)
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │  3. Draw         │  Render SVG elements:
  │     elements     │  boundary → ellipses → stick figures → lines → labels
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │  4. Apply        │  Apply classDef/style overrides
  │     styles       │
  └─────────────────┘
```

## 8. PNG Output

Mermaid produces SVG natively. For PNG rasterization, use `@mermaid-js/mermaid-cli`:

```bash
# Install
npm install -g @mermaid-js/mermaid-cli

# Convert to PNG
mmdc -i diagram.mmd -o diagram.png

# For large diagrams (30x30), increase dimensions:
mmdc -i diagram.mmd -o diagram.png --width 2000 --scale 2
```

Since mmdc renders any registered Mermaid diagram type, the plugin's SVG output is automatically supported. The plugin must register before mmdc processes the file — this is handled via a **mmdc config file**:

```json
// .mmdc-config.json
{
  "puppeteerConfig": {},
  "mermaidConfig": {
    "securityLevel": "loose"
  },
  "preScripts": ["mermaid-usecase-diagram/register"]
}
```

Or via a wrapper script:

```javascript
// render.mjs
import mermaid from 'mermaid';
import usecaseDiagram from 'mermaid-usecase-diagram';
mermaid.registerDiagram('usecaseDiagram', usecaseDiagram);
// mmdc invocation follows...
```

## 9. Grammar (Formal)

```
Diagram         := 'usecaseDiagram' NL Statement*
Statement       := ActorDecl | SystemBlock | Relationship | StyleDecl | Directive | Comment | NL

ActorDecl       := Side? 'actor' ID (AS Label)? NL
Side            := 'left' | 'right'
AS              := 'as'
Label           := QUOTED_STRING

SystemBlock     := 'system' QUOTED_STRING '{' NL UseCaseDecl* '}' NL
UseCaseDecl     := 'usecase' ID (AS Label)? NL

Relationship    := ID LinkType ID ('&' ID)* NL
LinkType        := '---' | '--->' | '--'

StyleDecl       := ClassDef | ClassApply | NodeStyle
ClassDef        := 'classDef' IDENT StyleProps NL
ClassApply      := 'class' IDList IDENT NL
NodeStyle       := 'style' ID StyleProps NL
StyleProps      := PropPair (',' PropPair)*
PropPair        := IDENT ':' VALUE
IDList          := ID (',' ID)*

Directive       := 'actorLayout' ('auto' | 'manual') NL

Comment         := '%%' .* NL

ID              := [a-zA-Z_][a-zA-Z0-9_]*
IDENT           := [a-zA-Z_][a-zA-Z0-9_-]*
QUOTED_STRING   := '"' [^"]* '"'
VALUE           := [^\s,]+
NL              := '\n'
```

## 10. Scale Considerations (30 Actors x 30 Use Cases)

### Estimated SVG dimensions

| Parameter | Value | Rationale |
|---|---|---|
| Ellipse height | ~66px | 120px width * 0.55 |
| Vertical gap | 20px | Between use cases |
| 30 use cases | ~2580px total | 30 * 66 + 29 * 20 |
| System boundary height | ~2640px | 2580 + 60px padding |
| Actor column width | ~160px each side | 100px label + 60px gap |
| System boundary width | ~200px | 120px ellipse + 80px padding |
| **Total SVG** | **~520w x 2700h px** | Portrait orientation |

At 2x scale PNG: **~1040 x 5400 px** — large but manageable.

### Performance considerations

- 30 actors + 30 use cases + ~60 relationships = ~120 SVG elements + ~60 lines — trivial for SVG/D3 rendering
- Parser processes ~80 lines of text — trivial
- Text measurement is the bottleneck (DOM-based) — batch measurements where possible

### Readability at scale

- With 30 use cases, the diagram is ~2.7m tall on screen — users will scroll
- Line crossings are inevitable but manageable with sensible declaration order
- Recommend: group related actors and use cases together in the source
- Future v2: consider pagination or collapsible sub-sections

## 11. Acceptance Criteria

A v1 implementation is complete when:

1. [ ] `usecaseDiagram` keyword is detected and parsed by the plugin
2. [ ] Actors render as UML stick figures on their declared side (left/right)
3. [ ] Use cases render as ellipses inside a system boundary rectangle
4. [ ] Three link types (`---`, `--->`, `--`) render correctly
5. [ ] Fan-out shorthand (`&`) works
6. [ ] `classDef`/`class`/`style` directives color actors and use cases
7. [ ] `actorLayout auto` positions actors at midpoint of connected UCs
8. [ ] `actorLayout manual` positions actors in declaration order
9. [ ] Unicode labels (Thai, CJK) render correctly
10. [ ] The full 30x30 example from Section 5 renders without layout breakdown
11. [ ] SVG output converts to PNG via mermaid-cli (mmdc)
12. [ ] Plugin registers via `mermaid.registerDiagram()` with no core modifications
13. [ ] The example from Section 5 produces output visually comparable to `USECASE-EXAMPLE-RENDER.jpg`