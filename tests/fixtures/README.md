# Test fixtures captured from the hosted NVIDIA endpoints

Captured 2026-10-17 with `tests/fixtures/capture.py` (three live calls). Regenerate the same way; never edit by hand.

| File | Source | Notes |
|---|---|---|
| `one_page.pdf` | hand-built by `capture.minimal_pdf` | One page, Helvetica, the Enterprise Support Policy text (3 headings, 7 lines). A sparser 3-line page made Parse 2.0 return empty content for 3,000 tokens, so the fixture page is deliberately realistic. |
| `rerank_response.json` | `POST .../llama-nemotron-rerank-vl-1b-v2/reranking` | 3 passages; `rankings` sorted by logit: index 1 (5.14), index 2 (-7.98), index 0 (-9.09). |
| `parse2_response.txt` | `nvidia/nemotron-parse-2.0`, prompt `</s><s><predict_bbox><predict_classes><output_markdown><predict_text_in_pic>`, `max_tokens` 2000, `temperature` 0 | Raw `message.content`. |
| `parse1_response.json` | `nvidia/nemotron-parse` with the `markdown_bbox` tool | `choices[0].message.tool_calls[0].function.arguments`: a JSON string holding a nested list `[[{bbox:{xmin,ymin,xmax,ymax}, text, type}, ...]]`. 9 elements. |

## Parse 2.0 grammar, confirmed against `parse2_response.txt`

NVIDIA's own `postprocessing.py` (Hugging Face repo `nvidia/NVIDIA-Nemotron-Parse-2.0`) extracts elements with:

```
<x_(\d+(?:\.\d+)?)><y_(\d+(?:\.\d+)?)>(.*?)<x_(\d+(?:\.\d+)?)><y_(\d+(?:\.\d+)?)><class_([^>]+)>   (re.DOTALL)
```

groups: x1, y1, text, x2, y2, class. The fixture yields **7 elements**, classes `Section-header` (3) and `Text` (4); all coordinates are in 0..1 (normalized to the model's letterboxed canvas). Elements are separated by blank lines. Line breaks inside a paragraph appear as `<br>`. No `<tbc>` or `<|unk|>` tokens and no `\begin{tabular}` in this fixture (tables come back as LaTeX on documents that have them; see the hosted docs example).

Request shape that works on the hosted endpoint: content parts in the order text, then one `image_url` (data URI or URL); `max_tokens` must leave room inside the model's 4,096-token context (the hosted docs use 1024; 2000 is safe; 4096 is rejected with a 400).
