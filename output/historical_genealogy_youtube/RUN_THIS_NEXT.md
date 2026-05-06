# RUN THIS NEXT

## Workflow
1. Open `final_scene_manifest.csv`.
2. For each row, copy the `Prompt` into Canva AI Image Generator.
3. Generate an image in 16:9.
4. Add optional text using `OverlayContent`.
5. Export images as `ALN-XXXX.png`.
6. Run:
   - `python main.py attach-canva-images --storyboard storyboard.json --images-dir <folder>`
   - `python main.py make-video --storyboard storyboard.json`

## Project title
Historical Genealogy Youtube
