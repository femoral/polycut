// Screen-space contour of the active-Part silhouette (#30).
//
// Samples the offscreen silhouette mask (the active Part's faces drawn flat on a
// transparent background) and outputs a teal ring where a pixel sits just outside the
// silhouette but a neighbour is inside it — a topology-independent outline of the
// projected Part, robust on the half-disconnected Meshy cut. Compiled to
// `contour.frag.qsb` with `pyside6-qsb`; ShaderEffect supplies the default vertex
// shader and `qt_TexCoord0`.
#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 texel;        // (1/width, 1/height) of the source texture
    float thickness;   // contour reach, in source pixels
    vec4 outline;      // teal, straight (non-premultiplied) RGBA
};

layout(binding = 1) uniform sampler2D source;

void main() {
    float here = texture(source, qt_TexCoord0).a;
    vec2 o = texel * thickness;
    float near = 0.0;
    near = max(near, texture(source, qt_TexCoord0 + vec2( o.x, 0.0)).a);
    near = max(near, texture(source, qt_TexCoord0 + vec2(-o.x, 0.0)).a);
    near = max(near, texture(source, qt_TexCoord0 + vec2(0.0,  o.y)).a);
    near = max(near, texture(source, qt_TexCoord0 + vec2(0.0, -o.y)).a);
    near = max(near, texture(source, qt_TexCoord0 + vec2( o.x,  o.y)).a);
    near = max(near, texture(source, qt_TexCoord0 + vec2(-o.x,  o.y)).a);
    near = max(near, texture(source, qt_TexCoord0 + vec2( o.x, -o.y)).a);
    near = max(near, texture(source, qt_TexCoord0 + vec2(-o.x, -o.y)).a);

    // Outer ring: a neighbour is inside the silhouette while this pixel is outside it.
    float edge = clamp(near - here, 0.0, 1.0);
    float a = edge * outline.a * qt_Opacity;
    fragColor = vec4(outline.rgb * a, a);  // premultiplied for Qt's blend
}
