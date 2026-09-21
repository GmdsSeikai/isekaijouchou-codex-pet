Create one horizontal animation strip for Codex pet `nemo-dango`, state `jumping`.

Use the attached canonical base for identity. Use the attached layout guide only for slot count, spacing, centering, and padding; do not draw the guide.

Output exactly 5 full-body frames in one left-to-right row on flat pure magenta #FF00FF. Treat the row as 5 invisible equal-width slots: one centered complete pose per slot, evenly spaced, with no overlap, clipping, empty slots, labels, or borders.

Identity: same pet in every frame: 日式二次元Q版少女桌宠，约2.5头身、头大身小、短肢体、紧凑全身轮廓。象牙白及腰长发，发尾略带淡金，厚刘海始终完整遮住角色右眼，只露出灰色左眼；两侧佩戴蓝色粉蝶花发饰。服装忠实提炼普遍体 Nemophila I：白色短款长羊腿袖罩衫，里面是蓝到白渐变的抹胸短裙，白色长袜，黑色高跟短靴；袖口、胸口与靴面各有三枚相连的金属圆环。神态安静、梦幻、略带神秘又亲切。造型必须像同一个完整角色，而不是动物或毛绒玩具；不得露出被遮住的右眼；不得出现文字、标志、武器或额外道具；所有服装部件与花饰必须连接在身体上并简化为小尺寸可读的大色块。. Preserve silhouette, face, proportions, markings, palette, material, style, and props.
Style: Pet-safe sprite: compact full-body mascot, readable in a 192x208 cell, clear silhouette, simple face, stable palette/materials, and crisp edges for chroma-key extraction. Style `sticker`: Polished sticker mascot with bold clean shapes, crisp outline, flat colors, and minimal highlight detail. User style notes: 高质量日式二次元Q版角色立绘，干净利落的动画线稿与赛璐璐上色，轻微柔和渐变；比例接近精致游戏桌宠而不是夸张表情包。保留原设优雅、纤细和克制的气质，同时保证192x208像素下脸、花饰、渐变裙和三连圆环清楚可辨。轮廓边缘清晰，无纸质白边。.
Animation continuity: keep apparent pet scale and baseline stable within the row unless the state itself intentionally changes vertical position, such as `jumping`. Move the pose within the slot instead of redrawing the pet larger or smaller frame to frame.

State action: Hover jump loop: anticipation, lift, airborne peak, descent, and settle through body height.

State requirements:
- Show the jump through pose and vertical body position only: anticipation, lift, airborne peak, descent, settle.
- Do not draw ground shadows, contact shadows, drop shadows, oval shadows, landing marks, dust, smears, bounce pads, or motion marks under the pet.
- Keep the background outside the pet perfectly flat chroma key with no darker key-colored patches.

Clean extraction: crisp opaque edges, safe padding, no scenery, text, guide marks, checkerboard, shadows, glows, motion blur, speed lines, dust, detached effects, stray pixels, or chroma-key colors inside the pet.
