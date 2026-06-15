pragma Singleton
import QtQuick

// Single source of truth for the Polycut design system (docs/design-system.md).
// Every component reads tokens from here — no hard-coded colors/sizes elsewhere —
// so the system can't drift as later slices add panels.
QtObject {
    id: theme

    // ---- Color tokens (neutral hue 230 + teal accent, sRGB) -------------
    readonly property color bg0: "#14171a"   // app background
    readonly property color bg1: "#1e2226"   // panels
    readonly property color bg2: "#282d32"   // raised surfaces, inputs
    readonly property color bg3: "#343b41"   // hover / borders-as-fill

    readonly property color fg0: "#f4f6f8"   // primary text, big numbers
    readonly property color fg1: "#c4c9ce"   // secondary text
    readonly property color fg2: "#8a9197"   // labels, muted (section headers)
    readonly property color fg3: "#5f666c"   // disabled, faint captions

    readonly property color teal: "#34d3c4"      // active, primary, badges
    readonly property color tealDim: "#2a8f88"   // accent pressed / track-fill
    readonly property color coral: "#f76d72"     // warnings (missing texture)
    readonly property color coralDim: "#c5545b"  // warning pressed

    readonly property color hairline: Qt.rgba(0.95, 0.96, 0.97, 0.10)

    // ---- Typography -----------------------------------------------------
    readonly property FontLoader _ui: FontLoader {
        source: Qt.resolvedUrl("fonts/Inter-Variable.ttf")
    }
    readonly property FontLoader _mono: FontLoader {
        source: Qt.resolvedUrl("fonts/JetBrainsMono-Variable.ttf")
    }
    readonly property string fontUi: _ui.name      // Inter — labels, buttons, body
    readonly property string fontMono: _mono.name  // JetBrains Mono — all numbers/data

    readonly property int fontMicro: 10  // version pill, chips, breadcrumb
    readonly property int fontSmall: 11
    readonly property int fontBase: 13
    readonly property int fontLg: 15        // app title
    readonly property int fontHeadline: 18  // empty-state headline
    readonly property int fontHero: 40      // the big face-count readout
    readonly property real headerSpacing: 1.4  // letter-spacing for SECTION HEADERS

    // icon glyph sizes (rail / empty-state / placeholder)
    readonly property int iconSm: 16
    readonly property int iconLg: 44

    // ---- Geometry / spacing / motion ------------------------------------
    readonly property int rSm: 8
    readonly property int rMd: 12
    readonly property int rLg: 18
    readonly property int rPanel: 14

    readonly property int rowHeight: 34
    readonly property int borderThin: 1
    readonly property int borderThick: 2
    readonly property int chipHeight: 20  // small uppercase mono pills (§6)
    readonly property int chipPadH: 12
    readonly property int dotSize: 8       // inline status indicator

    readonly property int pad: 14
    readonly property int gap: 11
    readonly property int gapXs: 6
    readonly property int sectionGap: 16

    readonly property int durFast: 140
    readonly property int durStandard: 220
    // standard ease cubic-bezier(0.22, 1, 0.36, 1); trailing 1,1 is the curve endpoint
    readonly property list<real> easeStandard: [0.22, 1.0, 0.36, 1.0, 1.0, 1.0]
}
