# Brand

A small, fixed set of assets. Everything is SVG except the social card, which
GitHub needs as a raster.

| File | What it is | Where it goes |
|---|---|---|
| [`mark.svg`](mark.svg) | The mark alone, 100 × 100 | favicon, avatar, anything under 200px |
| [`lockup.svg`](lockup.svg) | Mark plus wordmark | README header, slides, docs |
| [`social.svg`](social.svg) | 1280 × 640 source | edit this, then re-export |
| [`social.png`](social.png) | 1280 × 640 export | Settings → General → Social preview |

## The mark

Two quotation marks facing each other, with a line struck between them.

Two statements by one voice, and the later one cancelling the earlier. The
strike is the point: this contract does not judge a statement, it judges a
statement **against the record behind it**. A mark showing a single quotation
would be describing a different contract.

Built on a 100 × 100 grid. Stroke weight 8, round caps, corner radius 18. The
strike is chalk at 4, thinner than the marks and in a different colour, so it
reads as the relationship rather than as a third element.

- **Clear space:** half the mark height on every side.
- **Smallest size:** 18px alone, 24px locked to the wordmark. Verified — both
  quotation marks and the strike stay separable.
- **Never:** a second hue, a gradient, an outline version, a drop shadow, or the
  mark rotated. The geometry carries the meaning; rotating it breaks it.

## Palette

| Token | Hex | Use |
|---|---|---|
| ink | `#0C0D10` | the mark's field, any dark surface |
| chalk | `#E8E6E1` | the wordmark, primary text, the strike. Never pure white |
| accent | `#E0645C` | the quotation marks, one primary action, one live state |
| muted | `#9AA0A8` | secondary text |
| rule | `#232830` | hairlines and dividers |

One accent, used sparingly. On the social card it appears exactly three times:
the top bar, the mark, and the footer line.

The accent is distinct from its siblings on purpose: Crosscheck is violet
`#8B7CF6`, Tolerance green `#3DD68C`. Same grid, same stroke language, same
lockup geometry, different hue — so the set reads as one hand without reading as
one product.

## Type

**Inter**, weights 400 and 700, tracking tightened to −1.4 on the wordmark and
−2.6 at display size. Monospace for anything that is a value rather than a
sentence: `ui-monospace, SFMono-Regular, Menlo, monospace`. The wordmark is
always lowercase.

## Re-exporting the social card

```bash
pip install cairosvg
python -c "import cairosvg; cairosvg.svg2png(url='brand/social.svg', \
    write_to='brand/social.png', output_width=1280, output_height=640)"
```

Upload under **Settings → General → Social preview**. GitHub uses it whenever a
link to this repository is shared.

## Licence

MIT along with the rest of the repository. The name and mark identify this
specific primitive, so if you fork it and change what it does, change the name
too.
