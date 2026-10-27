# Gemini image-generation brief — Threadline Operations

## Art direction

Create small, realistic product catalog images for a fictional multi-category apparel retailer called **Threadline**. These images are supporting assets for a customer order-tracking preview only. The internal tool itself should rely primarily on tables, maps, event timelines and data visualizations; do not add decorative fashion campaign imagery to operational screens.

**Consistency requirements for every asset**
- Photorealistic premium e-commerce product photography, natural fabric/leather texture and believable construction.
- Clean warm off-white / very light grey background, soft studio lighting, subtle contact shadow, restrained editorial styling.
- One product per image, centered, full product visible, front or 3/4 angle, no model and no human body.
- No logos, brand names, labels, watermarks, words, price tags, UI, collage, hands, mannequins or fake text.
- Portrait 4:5 composition, high resolution (at least 1024 x 1280), consistent camera angle, scale and lighting across the collection.
- Save as WebP using the exact filenames below. Do not put text into the image.

## Master prompt (paste into Gemini)

> Generate one photorealistic premium e-commerce catalog photograph for a fictional multi-category clothing and accessories retailer. The product is: **[REPLACE WITH ONE PRODUCT BELOW]**. Single item only, centered with generous clean margins, full product visible, front three-quarter view, accurate material drape and stitching, premium but attainable quality, warm off-white seamless studio background, soft directional studio light from upper left and a subtle natural contact shadow. Editorial product photography, restrained neutral colour palette, realistic texture and construction, no dramatic lighting. Portrait 4:5, minimum 1024 x 1280, very sharp detail. Absolutely no logo, brand, letters, watermark, text, labels, hands, person, mannequin, packaging, collage, additional objects or UI. The image must be suitable as a small thumbnail in a real order-tracking page. Maintain the same studio setup and camera angle for every product in this set.

## Generate these six assets individually

1. **Filename:** `overshirt_olive.webp`  
   Product: Olive-green cotton utility overshirt, matte heavyweight cotton twill, button front, two clean chest pockets, relaxed but structured fit, no visible brand labels.

2. **Filename:** `trousers_stone.webp`  
   Product: Stone-coloured straight-leg cotton trousers, subtle woven twill texture, front waistband and pockets visible, neatly arranged as a product-only flat product photograph or invisible-form studio shot, no visible mannequin.

3. **Filename:** `outerwear_charcoal.webp`  
   Product: Charcoal lightweight utility jacket, clean modern cut, matte technical-cotton fabric, understated zip closure and discreet pockets, no logo.

4. **Filename:** `knit_crewneck_grey.webp`  
   Product: Mid-grey merino-blend crewneck knit sweater, believable fine-gauge knit texture, natural sleeve shape, no logo or label.

5. **Filename:** `sneaker_white.webp`  
   Product: Pair of clean off-white leather low-top sneakers, lightly textured leather, neutral sole, side three-quarter angle, no logos and no decorative marks.

6. **Filename:** `canvas_weekend_bag.webp`  
   Product: Natural canvas weekend bag with dark olive webbing handles and restrained hardware, structured but soft, no logo and no text.

7. **Filename:** `leather_belt_brown.webp`  
   Product: Medium-brown full-grain leather belt with a simple brushed-metal rectangular buckle, arranged in a natural loose curve, no logo or stamping.

8. **Filename:** `poplin_shirt_white.webp`  
   Product: Crisp white cotton poplin button-up shirt, product-only invisible-form presentation with the collar, placket, cuff and fabric texture clearly visible, no labels.

9. **Filename:** `polo_shirt_ecru.webp`  
   Product: Ecru cotton piqué polo shirt with a restrained collar and two-button placket, folded or invisible-form product presentation, no visible logo.

10. **Filename:** `woven_scarf_navy.webp`  
   Product: Navy wool-blend scarf with a fine woven texture and short natural fringe, loosely folded in a tidy product arrangement, no label or logo.

## Optional facility photography (not required for the MVP)

Only generate these if the product expands to a facility-detail drawer. Use landscape 16:9, realistic documentary photography, neutral industrial lighting and no readable signs, labels or brand logos:

- **`porto_factory_wide.webp`:** contemporary apparel production floor, cut fabric rolls, sewing workstations, garment inspection; clean, orderly and plausible, not futuristic, no identifiable people in close-up.
- **`distribution_centre_wide.webp`:** realistic regional distribution centre with apparel cartons, totes, barcode scanners and racking; safe aisle layout, no readable labels.
- **`materials_receiving_wide.webp`:** warehouse receiving bay with rolled fabric and packaging materials being checked against a shipment manifest; no readable text or branding.
- **`crossdock_loading_wide.webp`:** cross-dock facility with pallets, reusable totes and a parked linehaul trailer at a loading bay; credible European logistics environment.

Do not generate dashboard screenshots, maps, infographics or logos. Those should be rendered by the app itself using real UI components and data.
