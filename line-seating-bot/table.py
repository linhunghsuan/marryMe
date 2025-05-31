import json
import os
import math
from flask import Flask, render_template_string, request, redirect, url_for, send_file, session

# --- 核心佈局生成邏輯 (與上次提供的版本基本相同，已包含最新修正) ---
def generate_layout_data(
    params
):
    stage_location = params["stage_location"]
    stage_front_width_units = params["stage_front_width_units"]
    stage_alignment = params["stage_alignment"]
    guest_area_depth_units = params["guest_area_depth_units"]
    guest_area_width_units = params["guest_area_width_units"]
    numbering_primary_axis = params["numbering_primary_axis"]
    numbering_start_corner = params["numbering_start_corner"]
    head_table_specs = params.get("head_table_specs")

    STAGE_FIXED_DEPTH_UNITS = 2
    tables_data = {}
    layout_grid = []

    actual_grid_cols = 0
    actual_grid_rows = 0
    guest_area_x_start_internal, guest_area_y_start_internal = 0, 0
    guest_area_width_internal, guest_area_height_internal = 0, 0
    stage_occupies_horizontal_edge = True

    if stage_location in ["TOP", "BOTTOM"]:
        stage_occupies_horizontal_edge = True
        actual_grid_cols = guest_area_width_units
        actual_grid_rows = guest_area_depth_units + STAGE_FIXED_DEPTH_UNITS
        guest_area_width_internal = guest_area_width_units
        guest_area_height_internal = guest_area_depth_units
        guest_area_x_start_internal = 0
        guest_area_y_start_internal = STAGE_FIXED_DEPTH_UNITS if stage_location == "BOTTOM" else 0
    elif stage_location in ["LEFT", "RIGHT"]:
        stage_occupies_horizontal_edge = False
        actual_grid_cols = guest_area_depth_units + STAGE_FIXED_DEPTH_UNITS
        actual_grid_rows = guest_area_width_units
        guest_area_width_internal = guest_area_depth_units
        guest_area_height_internal = guest_area_width_units
        guest_area_y_start_internal = 0
        guest_area_x_start_internal = STAGE_FIXED_DEPTH_UNITS if stage_location == "LEFT" else 0
    else:
        raise ValueError("無效的舞台位置。")

    layout_grid = [[None for _ in range(actual_grid_cols)] for _ in range(actual_grid_rows)]

    # 2. 放置舞台
    stage_display_width = stage_front_width_units
    stage_penetration_depth = STAGE_FIXED_DEPTH_UNITS
    stage_w_on_grid, stage_h_on_grid = (stage_display_width, stage_penetration_depth) if stage_occupies_horizontal_edge else (stage_penetration_depth, stage_display_width)
    
    stage_w_on_grid = min(stage_w_on_grid, actual_grid_cols if stage_occupies_horizontal_edge else actual_grid_rows) 
    stage_h_on_grid = min(stage_h_on_grid, actual_grid_rows if stage_occupies_horizontal_edge else actual_grid_cols)


    sx, sy = 0, 0
    container_dim_for_stage_align = actual_grid_cols if stage_occupies_horizontal_edge else actual_grid_rows
    item_dim_for_stage_align = stage_w_on_grid if stage_occupies_horizontal_edge else stage_h_on_grid

    if stage_alignment == "LEFT": align_start_coord = 0
    elif stage_alignment == "RIGHT": align_start_coord = container_dim_for_stage_align - item_dim_for_stage_align
    elif stage_alignment == "CENTER_LEAN_RIGHT_TOP": align_start_coord = container_dim_for_stage_align - item_dim_for_stage_align - ((container_dim_for_stage_align - item_dim_for_stage_align) // 2)
    else: align_start_coord = (container_dim_for_stage_align - item_dim_for_stage_align) // 2

    if stage_occupies_horizontal_edge:
        sx = align_start_coord
        sy = 0 if stage_location == "BOTTOM" else actual_grid_rows - stage_h_on_grid
    else:
        sy = align_start_coord
        sx = 0 if stage_location == "LEFT" else actual_grid_cols - stage_w_on_grid
    
    sx = max(0, min(sx, actual_grid_cols - stage_w_on_grid))
    sy = max(0, min(sy, actual_grid_rows - stage_h_on_grid))

    for r_offset in range(stage_h_on_grid):
        for c_offset in range(stage_w_on_grid):
            y_coord, x_coord = sy + r_offset, sx + c_offset
            if 0 <= y_coord < actual_grid_rows and 0 <= x_coord < actual_grid_cols:
                layout_grid[y_coord][x_coord] = "STAGE"
                tables_data[f"Stage_{x_coord}_{y_coord}"] = {"position": [x_coord, y_coord], "type": "stage"}

    # 3. 放置主家席 (如果指定)
    if head_table_specs and head_table_specs.get("use_head_table"):
        ht_width = head_table_specs["width_units"]
        ht_depth = head_table_specs["depth_units"]
        ht_align = head_table_specs["alignment"]
        ht_gap_rows_from_stage = head_table_specs.get("gap_rows_from_stage", 0)
        ht_row_index_after_gap = head_table_specs.get("row_index_after_gap", 1)
        ht_block_leading_space = head_table_specs.get("block_leading_space", False)
        ht_blocks_area_behind = head_table_specs.get("blocks_area_behind", False)

        ht_x_base_coord, ht_y_base_coord = 0, 0
        ht_w_on_grid, ht_h_on_grid = 0, 0

        # A. 阻擋舞台和主家席之間的間隔排 (ht_gap_rows_from_stage)
        if ht_gap_rows_from_stage > 0:
            if stage_occupies_horizontal_edge:
                y_gap_block_start_idx = 0
                if stage_location == "BOTTOM": # 舞台在Y=0側, gap 在 guest_area_y_start_internal (即 STAGE_FIXED_DEPTH_UNITS) 之上
                    y_gap_block_start_idx = guest_area_y_start_internal
                else: # 舞台在 TOP, gap 在 guest_area 最頂部之下 (guest_area_y_start_internal + guest_area_height_internal - ht_gap_rows_from_stage)
                    y_gap_block_start_idx = guest_area_y_start_internal + guest_area_height_internal - ht_gap_rows_from_stage
                
                for i in range(ht_gap_rows_from_stage):
                    y_block_row = y_gap_block_start_idx + i
                    # 確保阻擋在賓客區內，且不超出原賓客區定義的間隔
                    if guest_area_y_start_internal <= y_block_row < guest_area_y_start_internal + guest_area_height_internal:
                        for x_b in range(guest_area_x_start_internal, guest_area_x_start_internal + guest_area_width_internal):
                             if 0 <= y_block_row < actual_grid_rows and 0 <= x_b < actual_grid_cols and layout_grid[y_block_row][x_b] is None:
                                layout_grid[y_block_row][x_b] = "BLOCKED"
            else: # 舞台 LEFT/RIGHT
                x_gap_block_start_idx = 0
                if stage_location == "LEFT":
                    x_gap_block_start_idx = guest_area_x_start_internal
                else: # RIGHT
                    x_gap_block_start_idx = guest_area_x_start_internal + guest_area_width_internal - ht_gap_rows_from_stage
                
                for i in range(ht_gap_rows_from_stage):
                    x_block_col = x_gap_block_start_idx + i
                    if guest_area_x_start_internal <= x_block_col < guest_area_x_start_internal + guest_area_width_internal:
                        for y_b in range(guest_area_y_start_internal, guest_area_y_start_internal + guest_area_height_internal):
                            if 0 <= y_b < actual_grid_rows and 0 <= x_block_col < actual_grid_cols and layout_grid[y_b][x_block_col] is None:
                                layout_grid[y_b][x_block_col] = "BLOCKED"
        
        # B. 計算主家席的基準放置座標 (在間隔之後，並考慮 ht_row_index_after_gap)
        # first_available_row_coord_after_gap / first_available_col_coord_after_gap: 間隔後的第一個可用座標(索引)
        if stage_occupies_horizontal_edge:
            ht_w_on_grid, ht_h_on_grid = ht_width, ht_depth
            first_available_row_coord_after_gap = 0
            if stage_location == "BOTTOM":
                first_available_row_coord_after_gap = guest_area_y_start_internal + ht_gap_rows_from_stage
                ht_y_base_coord = first_available_row_coord_after_gap + (ht_row_index_after_gap - 1)
            else: # TOP
                # 從賓客區頂部往下數 gap，再往下數 row_index
                first_available_row_coord_after_gap = guest_area_y_start_internal + guest_area_height_internal - ht_gap_rows_from_stage
                ht_y_base_coord = first_available_row_coord_after_gap - (ht_row_index_after_gap - 1) - ht_h_on_grid # ht_y_base_coord 是左下角Y

            eff_guest_depth_for_ht_calc = guest_area_height_internal - ht_gap_rows_from_stage
            if not (ht_row_index_after_gap >= 1 and (ht_row_index_after_gap - 1 + ht_h_on_grid) <= eff_guest_depth_for_ht_calc):
                 raise ValueError(f"主家席位置(在間隔後第{ht_row_index_after_gap}排,深{ht_h_on_grid}單位)超出可用賓客區深度({eff_guest_depth_for_ht_calc}單位)。")

            container_w_for_ht = guest_area_width_internal
            if ht_align == "ALIGN_LEFT": ht_x_base_coord = guest_area_x_start_internal
            elif ht_align == "ALIGN_RIGHT": ht_x_base_coord = guest_area_x_start_internal + container_w_for_ht - ht_w_on_grid
            elif ht_align == "CENTER_LEAN_RIGHT_TOP": ht_x_base_coord = guest_area_x_start_internal + container_w_for_ht - ht_w_on_grid - ((container_w_for_ht - ht_w_on_grid) // 2)
            else: ht_x_base_coord = guest_area_x_start_internal + (container_w_for_ht - ht_w_on_grid) // 2
            ht_x_base_coord = max(guest_area_x_start_internal, min(ht_x_base_coord, guest_area_x_start_internal + container_w_for_ht - ht_w_on_grid))
        else: # 舞台 LEFT/RIGHT
            ht_w_on_grid, ht_h_on_grid = ht_depth, ht_width
            first_available_col_coord_after_gap = 0
            if stage_location == "LEFT":
                first_available_col_coord_after_gap = guest_area_x_start_internal + ht_gap_rows_from_stage
                ht_x_base_coord = first_available_col_coord_after_gap + (ht_row_index_after_gap - 1)
            else: # RIGHT
                first_available_col_coord_after_gap = guest_area_x_start_internal + guest_area_width_internal - ht_gap_rows_from_stage
                ht_x_base_coord = first_available_col_coord_after_gap - (ht_row_index_after_gap - 1) - ht_w_on_grid

            eff_guest_width_for_ht_calc = guest_area_width_internal - ht_gap_rows_from_stage
            if not (ht_row_index_after_gap >= 1 and (ht_row_index_after_gap - 1 + ht_w_on_grid) <= eff_guest_width_for_ht_calc):
                 raise ValueError(f"主家席位置(在間隔後第{ht_row_index_after_gap}欄,寬{ht_w_on_grid}單位)超出可用賓客區寬度({eff_guest_width_for_ht_calc}單位)。")
            
            container_h_for_ht = guest_area_height_internal
            if ht_align == "ALIGN_LEFT": ht_y_base_coord = guest_area_y_start_internal
            elif ht_align == "ALIGN_RIGHT": ht_y_base_coord = guest_area_y_start_internal + container_h_for_ht - ht_h_on_grid
            elif ht_align == "CENTER_LEAN_RIGHT_TOP": ht_y_base_coord = guest_area_y_start_internal + container_h_for_ht - ht_h_on_grid - ((container_h_for_ht - ht_h_on_grid) // 2)
            else: ht_y_base_coord = guest_area_y_start_internal + (container_h_for_ht - ht_h_on_grid) // 2
            ht_y_base_coord = max(guest_area_y_start_internal, min(ht_y_base_coord, guest_area_y_start_internal + container_h_for_ht - ht_h_on_grid))

        # --- C. 阻擋主家席與「間隔區」之間的額外空間 (如果 ht_row_index_after_gap > 1 且用戶勾選) ---
        if ht_row_index_after_gap > 1 and ht_block_leading_space:
            if stage_occupies_horizontal_edge:
                # 額外空間的Y軸範圍
                y_leading_block_start, y_leading_block_end = 0, 0
                if stage_location == "BOTTOM":
                    y_leading_block_start = first_available_row_coord_after_gap # 間隔後的第一排
                    y_leading_block_end = ht_y_base_coord # 主家席開始的前一排
                else: # TOP
                    y_leading_block_start = ht_y_base_coord + ht_h_on_grid # 主家席結束的後一排 (Y值較大)
                    y_leading_block_end = first_available_row_coord_after_gap + ht_h_on_grid # 間隔後的第一排的結束 (Y值較大)
                                                                                            # 或者 guest_area_y_start_internal + guest_area_height_internal - ht_gap_rows_from_stage

                for y_lead_block in range(y_leading_block_start, y_leading_block_end):
                    for x_lead_block_offset in range(ht_w_on_grid): # 只阻擋主家席寬度內的格子
                        x_b = ht_x_base_coord + x_lead_block_offset
                        if 0 <= y_lead_block < actual_grid_rows and 0 <= x_b < actual_grid_cols and layout_grid[y_lead_block][x_b] is None:
                            layout_grid[y_lead_block][x_b] = "BLOCKED"
            else: # 舞台 LEFT/RIGHT
                x_leading_block_start, x_leading_block_end = 0, 0
                if stage_location == "LEFT":
                    x_leading_block_start = first_available_col_coord_after_gap
                    x_leading_block_end = ht_x_base_coord
                else: # RIGHT
                    x_leading_block_start = ht_x_base_coord + ht_w_on_grid
                    x_leading_block_end = first_available_col_coord_after_gap + ht_w_on_grid
                
                for x_lead_block in range(x_leading_block_start, x_leading_block_end):
                    for y_lead_block_offset in range(ht_h_on_grid):
                        y_b = ht_y_base_coord + y_lead_block_offset
                        if 0 <= y_b < actual_grid_rows and 0 <= x_lead_block < actual_grid_cols and layout_grid[y_b][x_lead_block] is None:
                            layout_grid[y_b][x_lead_block] = "BLOCKED"

        # --- D. 放置主家席並處理其「後方」阻擋 ---
        for r_offset in range(ht_h_on_grid):
            for c_offset in range(ht_w_on_grid):
                y, x = ht_y_base_coord + r_offset, ht_x_base_coord + c_offset
                if 0 <= y < actual_grid_rows and 0 <= x < actual_grid_cols:
                    if layout_grid[y][x] is None:
                        layout_grid[y][x] = "HEAD_TABLE"
                        tables_data[f"HeadTable_{x}_{y}"] = {"position": [x, y], "type": "head_table"}
                    
                    if ht_blocks_area_behind: # 只阻擋主家席「後方」
                        if stage_occupies_horizontal_edge:
                            if stage_location == "BOTTOM": # 舞台在下，主家席在其上，後方是 Y 更大的
                                for y_block in range(ht_y_base_coord + ht_h_on_grid, guest_area_y_start_internal + guest_area_height_internal):
                                    if 0 <= y_block < actual_grid_rows and x == (ht_x_base_coord + c_offset) and layout_grid[y_block][x] is None: layout_grid[y_block][x] = "BLOCKED"
                            else: # 舞台在上，主家席在其下，後方是 Y 更小的
                                for y_block in range(guest_area_y_start_internal, ht_y_base_coord):
                                    if 0 <= y_block < actual_grid_rows and x == (ht_x_base_coord + c_offset) and layout_grid[y_block][x] is None: layout_grid[y_block][x] = "BLOCKED"
                        else:
                            if stage_location == "LEFT": # 舞台在左，主家席在其右，後方是 X 更大的
                                for x_block in range(ht_x_base_coord + ht_w_on_grid, guest_area_x_start_internal + guest_area_width_internal):
                                    if 0 <= x_block < actual_grid_cols and y == (ht_y_base_coord + r_offset) and layout_grid[y][x_block] is None: layout_grid[y][x_block] = "BLOCKED"
                            else: # 舞台在右，主家席在其左，後方是 X 更小的
                                for x_block in range(guest_area_x_start_internal, ht_x_base_coord):
                                    if 0 <= x_block < actual_grid_cols and y == (ht_y_base_coord + r_offset) and layout_grid[y][x_block] is None: layout_grid[y][x_block] = "BLOCKED"

    # 4. 編號賓客桌位 (邏輯與上次相同)
    table_num_counter = 1
    eff_guest_x_min = guest_area_x_start_internal
    eff_guest_x_max = guest_area_x_start_internal + guest_area_width_internal
    eff_guest_y_min = guest_area_y_start_internal
    eff_guest_y_max = guest_area_y_start_internal + guest_area_height_internal

    x_coords_list = list(range(eff_guest_x_min, eff_guest_x_max))
    y_coords_list = list(range(eff_guest_y_min, eff_guest_y_max))

    if stage_location == "TOP":
        if numbering_start_corner.startswith("FRONT"): y_coords_list.reverse()
        if numbering_start_corner.endswith("RIGHT"): x_coords_list.reverse()
    elif stage_location == "BOTTOM":
        if numbering_start_corner.startswith("BACK"): y_coords_list.reverse()
        if numbering_start_corner.endswith("RIGHT"): x_coords_list.reverse()
    elif stage_location == "LEFT":
        if numbering_start_corner.startswith("BACK"): x_coords_list.reverse()
        if numbering_start_corner.endswith("RIGHT"): y_coords_list.reverse()
    elif stage_location == "RIGHT":
        if numbering_start_corner.startswith("FRONT"): x_coords_list.reverse()
        if numbering_start_corner.endswith("LEFT"): y_coords_list.reverse()

    primary_loop_is_internal_y = False
    if stage_occupies_horizontal_edge:
        if numbering_primary_axis == "TOWARDS_STAGE_AXIS": primary_loop_is_internal_y = True
    else:
        if numbering_primary_axis == "PARALLEL_TO_STAGE_AXIS": primary_loop_is_internal_y = True

    if primary_loop_is_internal_y:
        for y in y_coords_list:
            for x in x_coords_list:
                if eff_guest_y_min <= y < eff_guest_y_max and eff_guest_x_min <= x < eff_guest_x_max and layout_grid[y][x] is None:
                    layout_grid[y][x] = f"T{table_num_counter}"
                    tables_data[f"T{table_num_counter}"] = {"position": [x, y], "type": "normal"}
                    table_num_counter += 1
    else:
        for x in x_coords_list:
            for y in y_coords_list:
                if eff_guest_y_min <= y < eff_guest_y_max and eff_guest_x_min <= x < eff_guest_x_max and layout_grid[y][x] is None:
                    layout_grid[y][x] = f"T{table_num_counter}"
                    tables_data[f"T{table_num_counter}"] = {"position": [x, y], "type": "normal"}
                    table_num_counter += 1
                    
    # 5. 產生 HTML 預覽 (包含參數顯示)
    html = "<html><head><title>宴會廳桌位佈局</title><style>"
    html += "body { font-family: sans-serif, 'Microsoft JhengHei', 'SimSun'; display: flex; flex-direction: column; align-items: center; }"
    html += ".grid-container { display: grid; border: 1px solid #ccc; margin-bottom: 20px; }"
    html += ".grid-cell { width: 70px; height: 70px; border: 1px solid #eee; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; font-size: 11px; box-sizing: border-box; position: relative; overflow: hidden;}"
    html += ".cell-coord { position: absolute; top: 2px; left: 2px; font-size: 8px; color: #999; }"
    html += ".STAGE { background-color: #add8e6; font-weight:bold; }"
    html += ".HEAD_TABLE { background-color: #90ee90; font-weight:bold; }"
    html += ".BLOCKED { background-color: #ffcccb; background-image: repeating-linear-gradient(45deg, transparent, transparent 5px, #f0808030 5px, #f0808030 10px); }"
    html += ".normal-table-text { font-weight: bold; font-size: 14px;}"
    html += ".params-display { margin: 20px auto; padding: 15px; border: 1px dashed #ccc; background-color: #f9f9f9; width: 80%; max-width: 680px; text-align: left;}" # text-align: left for list items
    html += ".params-display h3 { margin-top: 0; text-align: center; }"
    html += ".params-display ul { list-style-type: none; padding-left: 0;}";
    html += ".params-display li { margin-bottom: 5px; }"
    html += "</style></head><body>"
    html += "<div style='width: 95%; max-width: 1000px; margin: auto;'>" # 包裹整個頁面內容使其置中
    html += f"<h1>宴會廳桌位佈局 (舞台位於: {params['stage_location']})</h1>"
    html += f"<h3 style='text-align:center;'>內部網格尺寸: {actual_grid_cols} 欄 x {actual_grid_rows} 排 (內部(0,0)為左下角)</h3>"
    
    html += f"<div class='grid-container' style='grid-template-columns: repeat({actual_grid_cols}, 70px); margin: 20px auto;'>" # 網格也置中
    for r_internal in reversed(range(actual_grid_rows)):
        for c_internal in range(actual_grid_cols):
            cell_content = layout_grid[r_internal][c_internal]
            cell_text, cell_class, text_span_class = "", "", ""
            if isinstance(cell_content, str):
                if cell_content.startswith("T"): cell_text, text_span_class = cell_content, "normal-table-text"
                elif cell_content == "STAGE": cell_text, cell_class = "舞台", "STAGE"
                elif cell_content == "HEAD_TABLE": cell_text, cell_class = "主家席", "HEAD_TABLE"
                elif cell_content == "BLOCKED": cell_text, cell_class = "預留", "BLOCKED"
            html += f"<div class='grid-cell {cell_class}'><span class='cell-coord'>({c_internal},{r_internal})</span><span class='{text_span_class}'>{cell_text}</span></div>"
    html += "</div>"

    # --- 顯示使用者參數 ---
    html += "<div class='params-display'>"
    html += "<h3>本次佈局使用參數:</h3><ul>"
    param_labels = {
        "stage_location": "舞台位置", "stage_front_width_units": "舞台正面寬度 (單位)", "stage_alignment": "舞台對齊方式",
        "guest_area_depth_units": "賓客區深度 (排)", "guest_area_width_units": "賓客區寬度 (桌/排)",
        "numbering_primary_axis": "主要編號軸向", "numbering_start_corner": "編號起始角落"
    }
    param_value_maps = {
        "stage_location": {"TOP": "最上方 (遠端)", "BOTTOM": "最下方 (近端)", "LEFT": "最左邊", "RIGHT": "最右邊"},
        "stage_alignment": {"CENTER_LEAN_LEFT_BOTTOM": "置中 (奇數寬時偏左/下)", "CENTER_LEAN_RIGHT_TOP": "置中 (奇數寬時偏右/上)", "LEFT": "靠左/下", "RIGHT": "靠右/上"},
        "numbering_primary_axis": {"TOWARDS_STAGE_AXIS": "優先沿「朝向舞台」方向", "PARALLEL_TO_STAGE_AXIS": "優先沿「平行舞台」方向"},
        "numbering_start_corner": {"BACK_LEFT": "遠離舞台的左側 (後左)", "BACK_RIGHT": "遠離舞台的右側 (後右)", "FRONT_LEFT": "靠近舞台的左側 (前左)", "FRONT_RIGHT": "靠近舞台的右側 (前右)"}
    }
    for key, label in param_labels.items():
        value = params[key]
        display_value = param_value_maps.get(key, {}).get(value, value)
        html += f"<li>{label}: {display_value}</li>"

    if params.get('head_table_specs') and params['head_table_specs'].get('use_head_table'):
        ht = params['head_table_specs']
        ht_align_display = param_value_maps.get("stage_alignment", {}).get(ht['alignment'], ht['alignment']) # 沿用舞台對齊的翻譯
        html += "<li>主家席: 已啟用<ul>"
        html += f"<li>與舞台間隔排數 (預留): {ht['gap_rows_from_stage']} 排</li>"
        html += f"<li>在間隔後第 {ht['row_index_after_gap']} 排開始 (於可用空間)</li>"
        html += f"<li>寬度: {ht['width_units']} 單位, 深度: {ht['depth_units']} 單位</li>"
        html += f"<li>對齊方式: {ht_align_display}</li>"
        html += f"<li>阻擋主家席與間隔區之間額外空間: {'是' if ht.get('block_leading_space', False) else '否'}</li>"
        html += f"<li>阻擋主家席後方空間: {'是' if ht['blocks_area_behind'] else '否'}</li></ul></li>"
    else:
        html += "<li>主家席: 未啟用</li>"
    html += "</ul></div>"
    # --- 參數顯示結束 ---

    html += "<h2 style='text-align:center;'>生成的 JSON 數據 (table_locations.json):</h2>"
    html += f"<pre style='background-color: #f0f0f0; padding:10px; border-radius:5px; white-space: pre-wrap; word-wrap: break-word; margin: 0 auto; width: 80%; max-width: 680px;'>{json.dumps(tables_data, indent=4, ensure_ascii=False)}</pre>"
    html += "</div></body></html>" # 結束最外層的置中 div

    try:
        with open("table_locations.json", "w", encoding="utf-8") as f:
            json.dump(tables_data, f, ensure_ascii=False, indent=4)
    except IOError as e:
        raise IOError(f"寫入 table_locations.json 時發生錯誤: {e}")

    return html, tables_data

# --- Flask Web 介面部分 ---
app = Flask(__name__)
app.secret_key = os.urandom(24) 

HTML_FORM_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <title>宴會廳桌位佈局產生器</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif, 'Microsoft JhengHei', 'SimSun'; margin: 0; padding: 0; background-color: #f8f9fa; color: #333; display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; }
        .page-container { width: 90%; max-width: 700px; margin-top: 20px; margin-bottom: 20px;}
        .form-container { background-color: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 6px 20px rgba(0,0,0,0.1); }
        h1 { color: #007bff; text-align: center; margin-bottom: 10px; font-size: 2em;}
        h2 { color: #495057; margin-top: 25px; margin-bottom:15px; border-bottom: 2px solid #007bff; padding-bottom: 8px; font-size: 1.5em;}
        label { display: block; margin-top: 15px; margin-bottom: 5px; font-weight: 600; color: #555; }
        input[type="number"], select { width: 100%; padding: 12px; margin-top: 5px; border: 1px solid #ced4da; border-radius: 6px; box-sizing: border-box; font-size: 1em; transition: border-color 0.3s; }
        input[type="number"]:focus, select:focus { border-color: #007bff; outline: none; box-shadow: 0 0 0 0.2rem rgba(0,123,255,.25); }
        .button-group { margin-top: 30px; display: flex; justify-content: space-between; }
        input[type="submit"], button[type="button"] { padding: 12px 25px; border: none; border-radius: 6px; cursor: pointer; font-size: 1.1em; font-weight: 500; transition: background-color 0.3s, transform 0.1s; }
        input[type="submit"] { background-color: #28a745; color: white; }
        input[type="submit"]:hover { background-color: #218838; transform: translateY(-1px); }
        button[type="button"] { background-color: #ffc107; color: #212529; }
        button[type="button"]:hover { background-color: #e0a800; transform: translateY(-1px); }
        .checkbox-label { display: inline-block; margin-left: 8px; font-weight: normal; vertical-align: middle; }
        input[type="checkbox"] { vertical-align: middle; width: auto; margin-right: 0;}
        .form-section { margin-bottom: 25px; padding: 20px; background-color: #fdfdfd; border: 1px solid #e9ecef; border-radius: 8px; }
        .error { color: #dc3545; background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 10px; border-radius: 6px; margin-top: 15px; font-size: 0.95em; }
        .sub-options { margin-left: 25px; padding-left: 15px; border-left: 2px solid #007bff; margin-top:10px; display: none; }
        .sub-options.active { display: block; }
        .tooltip { position: relative; display: inline-block; cursor: help; font-weight:normal; font-size:0.9em; color: #007bff; margin-left: 5px;}
        .tooltip .tooltiptext { visibility: hidden; width: 250px; background-color: #333; color: #fff; text-align: left; border-radius: 6px; padding: 8px; position: absolute; z-index: 1; bottom: 125%; left: 50%; margin-left: -125px; opacity: 0; transition: opacity 0.3s; font-size: 0.85em; line-height:1.4; }
        .tooltip:hover .tooltiptext { visibility: visible; opacity: 0.95; }
    </style>
</head>
<body>
    <div class="page-container">
    <div class="form-container">
        <h1>宴會廳桌位佈局產生器 🍽️</h1>
        <form method="post" id="layoutForm">
            <div class="form-section">
                <h2>舞台設定</h2>
                <label for="stage_location">舞台位置 (賓客面向此方向):</label>
                <select name="stage_location" id="stage_location">
                    <option value="TOP" {% if form_data.stage_location == "TOP" %}selected{% endif %}>最上方 (遠端)</option>
                    <option value="BOTTOM" {% if form_data.stage_location == "BOTTOM" %}selected{% endif %}>最下方 (近端)</option>
                    <option value="LEFT" {% if form_data.stage_location == "LEFT" %}selected{% endif %}>最左邊</option>
                    <option value="RIGHT" {% if form_data.stage_location == "RIGHT" %}selected{% endif %}>最右邊</option>
                </select>

                <label for="stage_front_width_units">舞台正面寬度 (桌位單位數):</label>
                <input type="number" name="stage_front_width_units" id="stage_front_width_units" value="{{ form_data.stage_front_width_units }}" min="1" required>
                
                <label for="stage_alignment">舞台對齊方式 (在其所在邊緣):</label>
                <select name="stage_alignment" id="stage_alignment">
                    <option value="CENTER_LEAN_LEFT_BOTTOM" {% if form_data.stage_alignment == "CENTER_LEAN_LEFT_BOTTOM" %}selected{% endif %}>置中 (奇數寬時偏左/下)</option>
                    <option value="CENTER_LEAN_RIGHT_TOP" {% if form_data.stage_alignment == "CENTER_LEAN_RIGHT_TOP" %}selected{% endif %}>置中 (奇數寬時偏右/上)</option>
                    <option value="LEFT" {% if form_data.stage_alignment == "LEFT" %}selected{% endif %}>靠左/下 (依舞台邊緣)</option>
                    <option value="RIGHT" {% if form_data.stage_alignment == "RIGHT" %}selected{% endif %}>靠右/上 (依舞台邊緣)</option>
                </select>
            </div>

            <div class="form-section">
                <h2>賓客區設定</h2>
                <label for="guest_area_depth_units">賓客區深度 (垂直於舞台的排數):</label>
                <input type="number" name="guest_area_depth_units" id="guest_area_depth_units" value="{{ form_data.guest_area_depth_units }}" min="1" required>

                <label for="guest_area_width_units">賓客區寬度 (平行於舞台的每排桌數):</label>
                <input type="number" name="guest_area_width_units" id="guest_area_width_units" value="{{ form_data.guest_area_width_units }}" min="1" required>
            </div>

            <div class="form-section">
                <h2>桌號編排方式</h2>
                <label for="numbering_primary_axis">主要編號軸向:</label>
                <select name="numbering_primary_axis" id="numbering_primary_axis">
                    <option value="TOWARDS_STAGE_AXIS" {% if form_data.numbering_primary_axis == "TOWARDS_STAGE_AXIS" %}selected{% endif %}>優先沿「朝向舞台」方向</option>
                    <option value="PARALLEL_TO_STAGE_AXIS" {% if form_data.numbering_primary_axis == "PARALLEL_TO_STAGE_AXIS" %}selected{% endif %}>優先沿「平行舞台」方向</option>
                </select>

                <label for="numbering_start_corner">編號起始角落 (賓客區中，面向舞台時):</label>
                <select name="numbering_start_corner" id="numbering_start_corner">
                    <option value="BACK_LEFT" {% if form_data.numbering_start_corner == "BACK_LEFT" %}selected{% endif %}>遠離舞台的左側 (後左)</option>
                    <option value="BACK_RIGHT" {% if form_data.numbering_start_corner == "BACK_RIGHT" %}selected{% endif %}>遠離舞台的右側 (後右)</option>
                    <option value="FRONT_LEFT" {% if form_data.numbering_start_corner == "FRONT_LEFT" %}selected{% endif %}>靠近舞台的左側 (前左)</option>
                    <option value="FRONT_RIGHT" {% if form_data.numbering_start_corner == "FRONT_RIGHT" %}selected{% endif %}>靠近舞台的右側 (前右)</option>
                </select>
            </div>
            
            <div class="form-section">
                <h2>(可選) 主家席設定</h2>
                <input type="checkbox" name="use_head_table" id="use_head_table" value="yes" {% if form_data.use_head_table %}checked{% endif %} onchange="toggleHeadTableOptions()">
                <label for="use_head_table" class="checkbox-label">啟用主家席</label>

                <div id="head_table_options" class="sub-options {% if form_data.use_head_table %}active{% endif %}">
                    <label for="ht_gap_rows_from_stage">與舞台之間間隔的「賓客席排數」(0表示不間隔，這些間隔排會被預留):</label>
                    <input type="number" name="ht_gap_rows_from_stage" id="ht_gap_rows_from_stage" value="{{ form_data.ht_gap_rows_from_stage }}" min="0">

                    <label for="ht_row_index_after_gap">主家席位於「間隔後可用賓客區」的第幾排開始 (1代表第一排):
                        <span class="tooltip">?<span class="tooltiptext">指主家席從「間隔區」之後的第幾排賓客區空間開始。例如：若間隔1排，此處設1，則主家席在「間隔排」後的第1排。若此處設2，則主家席與「間隔排」之間又會空出1排賓客席空間 (是否阻擋此額外空間由下方選項決定)。</span></span>
                    </label>
                    <input type="number" name="ht_row_index_after_gap" id="ht_row_index_after_gap" value="{{ form_data.ht_row_index_after_gap }}" min="1">
                    
                    <input type="checkbox" name="ht_block_leading_space" id="ht_block_leading_space" value="yes" {% if form_data.ht_block_leading_space %}checked{% endif %}>
                    <label for="ht_block_leading_space" class="checkbox-label">是否阻擋「主家席」與「間隔區」之間，與主家席同寬的額外空間 (僅當上述排數>1時有效)</label><br>

                    <label for="ht_width_units" style="margin-top:10px;">主家席寬度 (桌位單位數):</label>
                    <input type="number" name="ht_width_units" id="ht_width_units" value="{{ form_data.ht_width_units }}" min="1">
                    
                    <label for="ht_depth_units">主家席深度 (桌位單位數):</label>
                    <input type="number" name="ht_depth_units" id="ht_depth_units" value="{{ form_data.ht_depth_units }}" min="1">

                    <label for="ht_alignment">主家席對齊方式 (在其所在排):</label>
                    <select name="ht_alignment" id="ht_alignment">
                        <option value="CENTER_LEAN_LEFT_BOTTOM" {% if form_data.ht_alignment == "CENTER_LEAN_LEFT_BOTTOM" %}selected{% endif %}>置中 (奇數寬時偏左/下)</option>
                        <option value="CENTER_LEAN_RIGHT_TOP" {% if form_data.ht_alignment == "CENTER_LEAN_RIGHT_TOP" %}selected{% endif %}>置中 (奇數寬時偏右/上)</option>
                        <option value="ALIGN_LEFT" {% if form_data.ht_alignment == "ALIGN_LEFT" %}selected{% endif %}>靠左/下 (依該排方向)</option>
                        <option value="ALIGN_RIGHT" {% if form_data.ht_alignment == "ALIGN_RIGHT" %}selected{% endif %}>靠右/上 (依該排方向)</option>
                    </select>
                    <br>
                    <input type="checkbox" name="blocks_area_behind" id="blocks_area_behind" value="yes" {% if form_data.blocks_area_behind %}checked{% endif %} style="margin-top:10px;">
                    <label for="blocks_area_behind" class="checkbox-label">是否阻擋其「後方」(更遠離舞台方向) 同欄/列的桌位</label>
                </div>
            </div>
            {% if error_message %}
                <p class="error">{{ error_message }}</p>
            {% endif %}
            <div class="button-group">
                <button type="button" onclick="resetToDefaults()">恢復預設值</button>
                <input type="submit" value="產生佈局">
            </div>
        </form>
        <script>
            const defaultValues = {{ default_values_json | safe }};
            function toggleHeadTableOptions() {
                const useHtCheckbox = document.getElementById('use_head_table');
                const htOptionsDiv = document.getElementById('head_table_options');
                if (useHtCheckbox.checked) {
                    htOptionsDiv.classList.add('active');
                } else {
                    htOptionsDiv.classList.remove('active');
                }
            }
            function resetToDefaults() {
                for (const key in defaultValues) {
                    const element = document.getElementById(key) || document.getElementsByName(key)[0];
                    if (element) {
                        if (element.type === 'checkbox') {
                            element.checked = defaultValues[key];
                        } else {
                            element.value = defaultValues[key];
                        }
                    }
                }
                toggleHeadTableOptions();
            }
            document.addEventListener('DOMContentLoaded', toggleHeadTableOptions);
        </script>
    </div>
    </div>
</body>
</html>
"""

DEFAULT_FORM_VALUES = {
    "stage_location": "TOP",
    "stage_front_width_units": 4,
    "stage_alignment": "CENTER_LEAN_LEFT_BOTTOM",
    "guest_area_depth_units": 8,
    "guest_area_width_units": 5,
    "numbering_primary_axis": "TOWARDS_STAGE_AXIS",
    "numbering_start_corner": "BACK_LEFT",
    "use_head_table": False,
    "ht_gap_rows_from_stage": 0,
    "ht_row_index_after_gap": 1,
    "ht_block_leading_space": False,
    "ht_width_units": 2,
    "ht_depth_units": 1,
    "ht_alignment": "CENTER_LEAN_LEFT_BOTTOM",
    "blocks_area_behind": False
}

@app.route('/', methods=['GET', 'POST'])
def index():
    error_message = session.pop('error_message', None) 
    form_data_to_render = session.get('form_data', DEFAULT_FORM_VALUES.copy())

    if request.method == 'POST':
        current_form_data = request.form.to_dict(flat=True) 
        # 確保 checkbox 的值被正確處理 (如果未勾選，request.form 中不會有該 key)
        current_form_data['use_head_table'] = 'use_head_table' in request.form
        current_form_data['blocks_area_behind'] = 'blocks_area_behind' in request.form
        current_form_data['ht_block_leading_space'] = 'ht_block_leading_space' in request.form
        
        session['form_data'] = current_form_data # 儲存當前提交的數據以供錯誤時回填

        try:
            # 從 current_form_data 準備傳給核心函數的參數字典
            params_for_generation = {
                "stage_location": current_form_data['stage_location'],
                "stage_front_width_units": int(current_form_data['stage_front_width_units']),
                "stage_alignment": current_form_data['stage_alignment'],
                "guest_area_depth_units": int(current_form_data['guest_area_depth_units']),
                "guest_area_width_units": int(current_form_data['guest_area_width_units']),
                "numbering_primary_axis": current_form_data['numbering_primary_axis'],
                "numbering_start_corner": current_form_data['numbering_start_corner'],
                "head_table_specs": None
            }

            if current_form_data.get('use_head_table'):
                ht_gap = int(current_form_data.get('ht_gap_rows_from_stage', 0))
                ht_row_idx = int(current_form_data.get('ht_row_index_after_gap', 1))
                ht_block_lead = current_form_data.get('ht_block_leading_space', False)
                ht_w = int(current_form_data.get('ht_width_units', 2))
                ht_d = int(current_form_data.get('ht_depth_units', 1))
                ht_align = current_form_data.get('ht_alignment', "CENTER_LEAN_LEFT_BOTTOM")
                ht_blocks_bh = current_form_data.get('blocks_area_behind', False)
                
                if ht_w < 1 or ht_d < 1 or ht_gap < 0 or ht_row_idx < 1:
                     raise ValueError("主家席的寬度、深度、起始排數或間隔排數不能小於其最小值。")
                
                params_for_generation["head_table_specs"] = {
                    "use_head_table": True, # 標記啟用
                    "gap_rows_from_stage": ht_gap,
                    "row_index_after_gap": ht_row_idx,
                    "block_leading_space": ht_block_lead,
                    "width_units": ht_w,
                    "depth_units": ht_d,
                    "alignment": ht_align,
                    "blocks_area_behind": ht_blocks_bh
                }
            
            # 基本驗證
            if params_for_generation["stage_front_width_units"] < 1 or \
               params_for_generation["guest_area_depth_units"] < 1 or \
               params_for_generation["guest_area_width_units"] < 1:
                raise ValueError("舞台寬度、賓客區深度、賓客區寬度必須至少為 1。")
            
            # 更多驗證，例如舞台寬度/主家席寬度不應大於其容器寬度 (若置中)
            temp_stage_loc = params_for_generation["stage_location"]
            temp_guest_w = params_for_generation["guest_area_width_units"]
            temp_guest_d = params_for_generation["guest_area_depth_units"]

            container_width_for_stage = temp_guest_w if temp_stage_loc in ["TOP", "BOTTOM"] else temp_guest_d
            if params_for_generation["stage_alignment"].startswith("CENTER") and params_for_generation["stage_front_width_units"] > container_width_for_stage:
                 raise ValueError(f"置中的舞台正面寬度 ({params_for_generation['stage_front_width_units']}) 不能超過其所在方向的可用寬度 ({container_width_for_stage})。")
            
            if params_for_generation["head_table_specs"]:
                ht = params_for_generation["head_table_specs"]
                container_width_for_ht = temp_guest_w if temp_stage_loc in ["TOP", "BOTTOM"] else temp_guest_d
                if ht["alignment"].startswith("CENTER") and ht["width_units"] > container_width_for_ht:
                    raise ValueError(f"置中的主家席寬度 ({ht['width_units']}) 不能超過其所在方向的可用寬度 ({container_width_for_ht})。")

            html_preview_content, generated_json_data = generate_layout_data(params_for_generation)
            
            session['preview_html'] = html_preview_content
            # session['last_params_for_preview'] 已被嵌入 HTML，不再需要單獨傳遞
            return redirect(url_for('show_preview'))

        except ValueError as e:
            session['error_message'] = str(e)
            # session['form_data'] 已經在 POST 開始時儲存了用戶的原始輸入
            return redirect(url_for('index')) # 重定向回 GET 請求以顯示錯誤和保留的數據
        except Exception as e: # 捕捉其他可能的錯誤
            app.logger.error(f"產生佈局時發生未預期錯誤: {e}", exc_info=True)
            session['error_message'] = f"產生佈局時發生未預期錯誤，請檢查參數。({type(e).__name__})"
            return redirect(url_for('index'))

    # GET 請求時，使用 session 中的數據或預設值渲染表單
    # 需要確保 form_data_to_render 中的 checkbox 狀態是布林值
    processed_form_data = DEFAULT_FORM_VALUES.copy() # 先載入預設值
    if 'form_data' in session: # 如果 session 中有數據 (例如上次提交的或錯誤後保留的)
        temp_data = session.get('form_data')
        for key in processed_form_data: # 以預設值的 key 為準，從 temp_data 更新
            if key in temp_data:
                if isinstance(DEFAULT_FORM_VALUES.get(key), bool): # 處理 checkbox (布林值)
                    # request.form 對 checkbox 的處理是：勾選則有key，不勾選則無key。
                    # current_form_data 在 POST 時已將其轉為 True/False
                    processed_form_data[key] = temp_data[key] # 直接使用已轉換的布林值
                elif isinstance(DEFAULT_FORM_VALUES.get(key), int): # 處理數字
                    try: processed_form_data[key] = int(temp_data[key])
                    except (ValueError, TypeError): pass # 若轉換失敗，保留預設值
                else: # 處理字串 (select)
                    processed_form_data[key] = temp_data[key]
    
    return render_template_string(HTML_FORM_TEMPLATE, form_data=processed_form_data, default_values_json=json.dumps(DEFAULT_FORM_VALUES), error_message=error_message)


@app.route('/preview')
def show_preview():
    content = session.pop('preview_html', None)
    if content:
        download_link = f"<p style='text-align:center; margin-top:20px;'><a href='{url_for('download_json')}' download='table_locations.json' style='padding:10px 15px; background-color:#007bff; color:white; text-decoration:none; border-radius:5px;'>下載 table_locations.json</a></p>"
        back_link = "<p style='text-align:center; margin-top:10px;'><a href='/' style='color:#007bff; text-decoration:none;'>返回修改參數</a></p>"
        # 使用 div 包裹並設定 text-align:center 使內部塊級元素(如 h1, h3, .grid-container)也居中
        return "<div style='width:95%; max-width:1200px; margin: 20px auto; text-align:center;'>" + download_link + back_link + content + back_link + "</div>"
    else:
        return redirect(url_for('index')) # 如果沒有預覽內容，重導回首頁


@app.route('/download_json')
def download_json():
    # 確保路徑安全且正確
    base_dir = os.path.abspath(os.path.dirname(__file__))
    json_path = os.path.join(base_dir, "table_locations.json")
    if os.path.exists(json_path):
        return send_file(json_path, as_attachment=True, download_name="table_locations.json")
    else:
        session['error_message'] = "JSON 檔案不存在，請先成功產生佈局。"
        return redirect(url_for('index'))

if __name__ == '__main__':
    base_dir = os.path.abspath(os.path.dirname(__file__))
    json_file_path = os.path.join(base_dir, "table_locations.json")
    if not os.path.exists(json_file_path):
        print(f"提醒: {json_file_path} 不存在。首次成功產生佈局後會自動建立。")
    print("啟動宴會廳桌位佈局 Web 介面產生器...")
    print("請在您的網頁瀏覽器中開啟 http://127.0.0.1:5000/  (或您的伺服器IP:埠號)")
    app.run(host="0.0.0.0", port=5000, debug=True) # debug=True 方便開發，生產環境應設為 False