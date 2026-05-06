# Render with 3DStreet

How to turn a buildable-scenario GeoJSON into the source images for a before/after street visualization, using [3DStreet](https://3dstreet.app).

The goal is to make the workflow repeatable enough that anyone can produce a consistent set of artifacts for a new location.

## What you get per location

Four images, all framed from the **same camera pose**:

| File | What it is |
| --- | --- |
| `<location>-before-raw.png` | Geo 3D tiles only, building envelopes hidden |
| `<location>-before-render.png` | AI Render upscale of the raw tiles to a photorealistic street view |
| `<location>-massing.png` | Same camera pose, building envelopes visible |
| `<location>-future-render.png` | AI Render img2img on the massing snapshot — replaces solid color boxes with the future built scenario |

These four are the source assets that get composed into a social video (before → before+massing → future scenario, with a lower third). Producing the combined video is out of scope for this doc.

Nano Banana Pro is the default AI Render model in 3DStreet and returns the best results in our testing, but you can also experiment with other models.

## Prerequisites

- A 3DStreet account, signed in at <https://3dstreet.app>
- The buildable-scenario GeoJSON for this location loaded into a 3DStreet scene (see other docs in this repo)
- Decide a location and camera or think of a few ideas using 3DStreet, Google Maps, or other geospatial sources to frame your shots
- It's helpful to think about your destination for the output files, will they be downloaded to a local file and then shared on a cloud service?

## Workflow

### 1. Frame the camera once

Pick a vantage point that reads well — a recognizable corner, a clear view down the street, a landmark in frame. Feel free to capture multiple throwaway snapshots to find an appealing framing before you go ahead and select on one.

Do not move the camera again until all four images are saved.

### 2. Capture `before-raw`

Hide the building-envelope entities so only the geo 3D tiles remain. Capture the snapshot. Save as `<location>-before-raw.png`.

### 3. AI-render `before-raw` → `before-render`

Run an AI render on the raw snapshot to upscale the low-fidelity 3D tiles into a photorealistic street view.

Default prompt:

> Upscale the low fidelity 3d tiles imagery to a photorealistic street-level rendering.

If notable landmarks look low-fi (bridge, tower, foliage), name them explicitly:

> Upscale the low fidelity 3d tiles imagery to fix (the bridge and foliage) into a photorealistic rendering.

Save as `<location>-before-render.png`.

### 4. Capture `massing`

Restore the building envelopes. Without touching the camera, capture the snapshot. Save as `<location>-massing.png`.

### 5. AI-render `massing` → `future-render`

Run an img2img Nano Banana Pro render on the massing snapshot.

Default prompt:

> Replace the solid color boxes with photorealistic dense multi-unit residential housing while retaining the core geometry unmodified.

Variant if local context calls for landmark fixes:

> Upscale the low fidelity 3d tiles imagery to fix (the bridge and foliage) while replacing the solid color boxes with photorealistic dense multi-unit residential housing.

Save as `<location>-future-render.png`.

## Prompt-writing suggestions

You may not need a custom prompt -- in most cases, the default suggestions above work fine. But if you want to optimize custom image generation prompts, here are some suggestions these come from iterating across dozens of scenes.

- **State realism explicitly.** Use "photorealistic" or "realistic rendering"
- **Use a distinctive descriptor for the boxes.** "solid color" or "brightly colored artificial" both work. "primary color" was less reliable
- **Don't negate.** Adding "ONLY replace the color boxes, do not replace existing housing" did not improve results and sometimes made them worse. Spend the word budget on what you want, not what to avoid.
- **Be specific about geospatial fixes.** When 3D tiles are insufficient for a key landmark (bridge, tower, foliage), call it out by name in the prompt.

## Known gaps

- Camera pose is not yet persisted with snapshots — see [3DStreet/3dstreet#1605](https://github.com/3DStreet/3dstreet/issues/1605).
- Video composition (the 20s social cut combining the four images with a lower third) is not yet automated. Here's an example of output: https://www.tiktok.com/@kieranfarr/video/7586823465676590350

## Driving via MCP

You can have an LLM agent walk through the workflow above by pairing [Claude Code](https://docs.claude.com/en/docs/claude-code) (or another MCP client) to a 3DStreet tab via the [3dstreet-mcp](https://github.com/3DStreet/3dstreet-mcp) bridge.

### Setup

1. Install Claude Code.
2. Register the MCP: `claude mcp add 3dstreet -- npx -y 3dstreet-mcp`
3. Restart Claude Code so the MCP tools load.
4. Open <https://3dstreet.app>, sign in, load the GeoJSON for your location.
5. In the editor: AI Assistant tab → `/mcp` → click **Reconnect** until status is green.
6. Then, point the assistant at this doc:

> Read `RENDER_WITH_3DSTREET.md` and run the workflow for **\<location\>**, framing **\<framing\>**, saving outputs to **\<directory\>**. Confirm the framing with me after step 1 before continuing.
