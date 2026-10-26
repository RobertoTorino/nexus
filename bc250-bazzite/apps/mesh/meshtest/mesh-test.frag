// SPDX-License-Identifier: GPL-3.0-or-later
// The mesh test's fragment shader: the tile's colour, unchanged.
#version 460

layout(location = 0) flat in vec4 colour;
layout(location = 0) out vec4 result;

void main()
{
    result = colour;
}
