import json
import os
from flask import Flask, render_template_string, request, redirect, url_for, send_file, session, flash

# --- 核心佈局生成邏輯 ---
def generate_layout_data(params):
    errors = []
    warnings = []
    # --- 參數 ---
    stage_location = params.get("stage_location", "TOP")
    stage_front_width_units = max(1, params.get("stage_front_width_units", 1))
    stage_alignment = params.get("stage_alignment", "CENTER_LEAN_LEFT_BOTTOM")
    guest_area_depth_units = max(1, params.get("guest_area_depth_units", 1))
    guest_area_width_units = max(1, params.get("guest_area_width_units", 1))
    numbering_primary_axis = params.get("numbering_primary_axis", "TOWARDS_STAGE_AXIS")
    numbering_start_corner = params.get("numbering_start_corner", "BACK_LEFT")
    head_table_specs = params.get("head_table_specs")
    manual_block_coords_str = params.get("manual_block_coords_str", "[]")
    staggered_columns_str = params.get("staggered_columns_str", "[]")
    

    STAGE_FIXED_DEPTH_UNITS = 1
    tables_data = {}
    layout_grid = []

    staggered_cols_0_based = set()
    staggered_cols_0_based = set()
    try:
        staggered_columns_1_based = json.loads(staggered_columns_str)
        if isinstance(staggered_columns_1_based, list):
            for c in staggered_columns_1_based:
                if isinstance(c, (int, float, str)) and str(c).isdigit():
                    val = int(c)
                    if val > 0:
                        staggered_cols_0_based.add(val - 1)
                else:
                    warnings.append(f"忽略非整數索引值: {c} (type: {type(c).__name__})")
        else:
            warnings.append(f"交錯直行設定格式應為列表，但收到: {type(staggered_columns_1_based)}。已忽略。")
    except (json.JSONDecodeError, TypeError) as e:
        if staggered_columns_str and staggered_columns_str.strip() != '[]':
            warnings.append(f"解析交錯直行設定JSON時失敗: '{staggered_columns_str}'。錯誤: {str(e)}。已忽略。")



    actual_grid_cols = 0
    actual_grid_rows = 0
    guest_area_x_start_internal, guest_area_y_start_internal = 0, 0
    # guest_area_width_internal and guest_area_height_internal refer to the dimensions
    # of the guest seating area *on the grid*, which might be swapped depending on stage orientation.
    guest_area_width_internal, guest_area_height_internal = 0, 0 
    stage_occupies_horizontal_edge = True # True if stage is TOP or BOTTOM

    # Determine grid dimensions and guest area orientation based on stage location
    actual_grid_cols, actual_grid_rows = 0, 0
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
    actual_grid_cols = max(1, actual_grid_cols)
    actual_grid_rows = max(1, actual_grid_rows)
    layout_grid = [[None for _ in range(actual_grid_cols)] for _ in range(actual_grid_rows)]

    # Stage placement
    stage_display_width = stage_front_width_units # This is the width along the front edge
    stage_penetration_depth = STAGE_FIXED_DEPTH_UNITS # This is how "deep" the stage goes
    
    stage_w_on_grid, stage_h_on_grid = (stage_display_width, stage_penetration_depth) if stage_occupies_horizontal_edge else (stage_penetration_depth, stage_display_width)
    stage_w_on_grid = min(max(1, stage_w_on_grid), actual_grid_cols)
    stage_h_on_grid = min(max(1, stage_h_on_grid), actual_grid_rows)

    sx, sy = 0, 0 # Top-left coordinates of the stage on the grid
    container_dim_for_stage_align = actual_grid_cols if stage_occupies_horizontal_edge else actual_grid_rows
    item_dim_for_stage_align = stage_w_on_grid if stage_occupies_horizontal_edge else stage_h_on_grid
    
    # Calculate alignment start coordinate for the stage
    if stage_alignment in ["LEFT", "EDGE_TOP_OR_LEFT"]: align_start_coord = 0
    elif stage_alignment in ["RIGHT", "EDGE_BOTTOM_OR_RIGHT"]: align_start_coord = container_dim_for_stage_align - item_dim_for_stage_align
    elif stage_alignment == "CENTER_LEAN_RIGHT_TOP": align_start_coord = (container_dim_for_stage_align - item_dim_for_stage_align + 1) // 2
    else: align_start_coord = (container_dim_for_stage_align - item_dim_for_stage_align) // 2 # Default CENTER_LEAN_LEFT_BOTTOM

    if stage_occupies_horizontal_edge:
        sx = align_start_coord
        # If stage_location is "TOP", it means visually at the bottom of the venue (higher Y indices)
        # If stage_location is "BOTTOM", it means visually at the top of the venue (lower Y indices)
        sy = (actual_grid_rows - stage_h_on_grid) if stage_location == "TOP" else 0
    else: # Stage on LEFT or RIGHT
        sy = align_start_coord
        # If stage_location is "RIGHT", it means visually at the right of the venue (higher X indices)
        # If stage_location is "LEFT", it means visually at the left of the venue (lower X indices)
        sx = (actual_grid_cols - stage_w_on_grid) if stage_location == "RIGHT" else 0
    
    sx = max(0, min(sx, actual_grid_cols - stage_w_on_grid))
    sy = max(0, min(sy, actual_grid_rows - stage_h_on_grid))

    for r_offset in range(stage_h_on_grid):
        for c_offset in range(stage_w_on_grid):
            y_coord, x_coord = sy + r_offset, sx + c_offset
            if 0 <= y_coord < actual_grid_rows and 0 <= x_coord < actual_grid_cols:
                layout_grid[y_coord][x_coord] = "STAGE"
                tables_data[f"Stage_{x_coord}_{y_coord}"] = {"position": [x_coord, y_coord], "type": "stage"}

    head_table_placed_successfully = False
    if head_table_specs and head_table_specs.get("use_head_table"):
        ht_width = max(1, head_table_specs.get("width_units", 1)) # Width along the stage front
        ht_depth = max(1, head_table_specs.get("depth_units", 1)) # Depth away from stage
        ht_align = head_table_specs.get("alignment", "CENTER_LEAN_LEFT_BOTTOM")
        ht_gap_rows_from_stage = max(0, head_table_specs.get("gap_rows_from_stage", 0))
        # ht_row_index_in_zone: 0 is first row after gap, negative into gap, positive further into guest area
        ht_row_index_in_zone = head_table_specs.get("row_index_in_zone", 0) # Default changed to 0
        ht_block_leading_space = head_table_specs.get("block_leading_space", False)
        ht_blocks_area_behind = head_table_specs.get("blocks_area_behind", False)

        # Mark gap rows first
        if ht_gap_rows_from_stage > 0:
            if stage_occupies_horizontal_edge:
                # y_gap_block_start_idx: where the gap begins relative to guest area start
                if stage_location == "BOTTOM": # Stage at visual top (low Y), gap is after stage
                    y_gap_block_start_idx = guest_area_y_start_internal 
                else: # Stage at visual top (high Y), gap is before stage (from guest area perspective)
                    y_gap_block_start_idx = guest_area_y_start_internal + guest_area_height_internal - ht_gap_rows_from_stage
                
                for i in range(ht_gap_rows_from_stage):
                    y_block_row = y_gap_block_start_idx + i
                    # Ensure gap is within the guest area's allocated rows
                    if guest_area_y_start_internal <= y_block_row < guest_area_y_start_internal + guest_area_height_internal:
                        for x_b in range(guest_area_x_start_internal, guest_area_x_start_internal + guest_area_width_internal):
                            if 0 <= y_block_row < actual_grid_rows and 0 <= x_b < actual_grid_cols and layout_grid[y_block_row][x_b] is None:
                                layout_grid[y_block_row][x_b] = "BLOCKED_GAP"
            else: # Stage on LEFT or RIGHT
                if stage_location == "LEFT": # Stage at visual left (low X), gap is after stage
                    x_gap_block_start_idx = guest_area_x_start_internal
                else: # Stage at visual right (high X), gap is before stage
                    x_gap_block_start_idx = guest_area_x_start_internal + guest_area_width_internal - ht_gap_rows_from_stage

                for i in range(ht_gap_rows_from_stage):
                    x_block_col = x_gap_block_start_idx + i
                    if guest_area_x_start_internal <= x_block_col < guest_area_x_start_internal + guest_area_width_internal:
                        for y_b in range(guest_area_y_start_internal, guest_area_y_start_internal + guest_area_height_internal):
                            if 0 <= y_b < actual_grid_rows and 0 <= x_block_col < actual_grid_cols and layout_grid[y_b][x_block_col] is None:
                                layout_grid[y_b][x_block_col] = "BLOCKED_GAP"
        
        ht_x_base_coord_ideal, ht_y_base_coord_ideal = 0, 0
        ht_w_on_grid, ht_h_on_grid = 0, 0 # Actual HT dimensions on grid

        current_errors_count = len(errors)

        if stage_occupies_horizontal_edge:
            ht_w_on_grid, ht_h_on_grid = ht_width, ht_depth
            
            # X-alignment (horizontal alignment)
            container_w_for_ht_align = guest_area_width_internal
            if ht_align == "ALIGN_LEFT": temp_ht_x_offset = 0
            elif ht_align == "ALIGN_RIGHT": temp_ht_x_offset = container_w_for_ht_align - ht_w_on_grid
            elif ht_align == "CENTER_LEAN_RIGHT_TOP": temp_ht_x_offset = (container_w_for_ht_align - ht_w_on_grid + 1) // 2
            else: temp_ht_x_offset = (container_w_for_ht_align - ht_w_on_grid) // 2
            ht_x_base_coord_ideal = guest_area_x_start_internal + temp_ht_x_offset

            # Y-position based on ht_row_index_in_zone
            if stage_location == "BOTTOM": # Stage at visual top (low Y), guest area Y increases away from stage
                # Check if ht_row_index_in_zone tries to place HT into/before stage
                if ht_row_index_in_zone < -ht_gap_rows_from_stage:
                    errors.append(f"主桌設定 '於間隔區/後第幾排' ({ht_row_index_in_zone}) 太靠前，超出與舞台間隔 ({ht_gap_rows_from_stage} 排)。")
                
                ht_y_base_coord_ideal = guest_area_y_start_internal + ht_gap_rows_from_stage + ht_row_index_in_zone
                
                # Check if HT goes beyond guest area depth
                if ht_y_base_coord_ideal + ht_h_on_grid > guest_area_y_start_internal + guest_area_height_internal:
                     errors.append(f"主桌設定 '於間隔區/後第幾排' ({ht_row_index_in_zone}) 使主桌超出賓客區深度 ({guest_area_height_internal} 排)。")

            else: # stage_location == "TOP" (Stage at visual bottom (high Y), guest area Y decreases towards stage)
                if ht_row_index_in_zone < -ht_gap_rows_from_stage:
                    errors.append(f"主桌設定 '於間隔區/後第幾排' ({ht_row_index_in_zone}) 太靠前 (向舞台方向)，超出與舞台間隔 ({ht_gap_rows_from_stage} 排)。")

                # Anchor is the top-most row of the head table if ht_row_index_in_zone = 0
                # This is the row just "before" the gap, from guest area side
                base_y_for_ht_zone_0_top_edge = (guest_area_y_start_internal + guest_area_height_internal - ht_gap_rows_from_stage) - ht_h_on_grid
                ht_y_base_coord_ideal = base_y_for_ht_zone_0_top_edge - ht_row_index_in_zone

                # Check if HT goes beyond guest area depth (i.e. ht_y_base_coord_ideal < guest_area_y_start_internal)
                if ht_y_base_coord_ideal < guest_area_y_start_internal:
                    errors.append(f"主桌設定 '於間隔區/後第幾排' ({ht_row_index_in_zone}) 使主桌超出賓客區深度 (太靠近場地邊緣)。")
        
        else: # Stage on LEFT or RIGHT
            ht_w_on_grid, ht_h_on_grid = ht_depth, ht_width # ht_depth is width on grid, ht_width is height on grid
            
            # Y-alignment (vertical alignment)
            container_h_for_ht_align = guest_area_height_internal
            if ht_align == "ALIGN_LEFT": temp_ht_y_offset = 0 # Corresponds to Top
            elif ht_align == "ALIGN_RIGHT": temp_ht_y_offset = container_h_for_ht_align - ht_h_on_grid # Corresponds to Bottom
            elif ht_align == "CENTER_LEAN_RIGHT_TOP": temp_ht_y_offset = (container_h_for_ht_align - ht_h_on_grid + 1) // 2
            else: temp_ht_y_offset = (container_h_for_ht_align - ht_h_on_grid) // 2
            ht_y_base_coord_ideal = guest_area_y_start_internal + temp_ht_y_offset

            # X-position based on ht_row_index_in_zone
            if stage_location == "LEFT": # Stage at visual left (low X), guest area X increases
                if ht_row_index_in_zone < -ht_gap_rows_from_stage:
                    errors.append(f"主桌設定 '於間隔區/後第幾排' ({ht_row_index_in_zone}) 太靠前，超出與舞台間隔 ({ht_gap_rows_from_stage} 排)。")
                ht_x_base_coord_ideal = guest_area_x_start_internal + ht_gap_rows_from_stage + ht_row_index_in_zone
                
                if ht_x_base_coord_ideal + ht_w_on_grid > guest_area_x_start_internal + guest_area_width_internal:
                    errors.append(f"主桌設定 '於間隔區/後第幾排' ({ht_row_index_in_zone}) 使主桌超出賓客區寬度 ({guest_area_width_internal} 列)。")
            
            else: # stage_location == "RIGHT" (Stage at visual right (high X), guest area X decreases)
                if ht_row_index_in_zone < -ht_gap_rows_from_stage:
                    errors.append(f"主桌設定 '於間隔區/後第幾排' ({ht_row_index_in_zone}) 太靠前 (向舞台方向)，超出與舞台間隔 ({ht_gap_rows_from_stage} 排)。")
                
                base_x_for_ht_zone_0_left_edge = (guest_area_x_start_internal + guest_area_width_internal - ht_gap_rows_from_stage) - ht_w_on_grid
                ht_x_base_coord_ideal = base_x_for_ht_zone_0_left_edge - ht_row_index_in_zone

                if ht_x_base_coord_ideal < guest_area_x_start_internal:
                     errors.append(f"主桌設定 '於間隔區/後第幾排' ({ht_row_index_in_zone}) 使主桌超出賓客區寬度 (太靠近場地邊緣)。")

        # Final boundary checks for HT against overall grid and stage overlap
        # Only proceed if no errors from ht_row_index_in_zone calculations so far
        if len(errors) == current_errors_count:
            can_place_ht_atomically = True
            ht_candidate_cells = []

            for r_offset in range(ht_h_on_grid):
                for c_offset in range(ht_w_on_grid):
                    y, x = ht_y_base_coord_ideal + r_offset, ht_x_base_coord_ideal + c_offset
                    if not (0 <= y < actual_grid_rows and 0 <= x < actual_grid_cols):
                        errors.append(f"主桌部分單元格 ({x},{y}) 超出場地總範圍。")
                        can_place_ht_atomically = False
                        break
                    if layout_grid[y][x] == "STAGE":
                        errors.append(f"主桌位置 ({x},{y}) 與舞台重疊。")
                        can_place_ht_atomically = False
                        break
                    # Other unrecoverable overlaps can be checked here if necessary
                    ht_candidate_cells.append((x,y))
                if not can_place_ht_atomically: break
            
            if can_place_ht_atomically and len(errors) == current_errors_count:
                # Clamp coordinates just in case, though errors should prevent this if out of bounds
                ht_x_base_coord = max(0, min(ht_x_base_coord_ideal, actual_grid_cols - ht_w_on_grid))
                ht_y_base_coord = max(0, min(ht_y_base_coord_ideal, actual_grid_rows - ht_h_on_grid))

                for x_ht, y_ht in ht_candidate_cells: # Use actual coordinates from ideal if no clamping was needed
                     # Recalculate x_ht, y_ht based on clamped base coords if clamping happened
                    final_x = ht_x_base_coord + (x_ht - ht_x_base_coord_ideal)
                    final_y = ht_y_base_coord + (y_ht - ht_y_base_coord_ideal)

                    # Ensure the cell is still valid after potential clamping
                    if 0 <= final_y < actual_grid_rows and 0 <= final_x < actual_grid_cols:
                        if layout_grid[final_y][final_x] is None or layout_grid[final_y][final_x] == "BLOCKED_GAP":
                             layout_grid[final_y][final_x] = "HEAD_TABLE"
                             tables_data[f"HeadTable_{final_x}_{final_y}"] = {"position": [final_x, final_y], "type": "head_table"}
                    else:
                        errors.append(f"主桌單元格 ({final_x},{final_y}) 在最終放置時無效。")


                head_table_placed_successfully = True # Assuming placement happened if no new errors

                # Blocking leading space (between gap and head table, if HT is further into guest area)
                if ht_row_index_in_zone > 0 and ht_block_leading_space: # Only if HT is not in/before gap
                    if stage_occupies_horizontal_edge:
                        block_start_y, block_end_y = -1, -1
                        # ht_y_base_coord is the top of the HT
                        if stage_location == "BOTTOM": # Stage visual top, HT Y increases
                            # Block space from (gap_end) to (ht_start)
                            block_start_y = guest_area_y_start_internal + ht_gap_rows_from_stage
                            block_end_y = ht_y_base_coord 
                        else: # Stage visual bottom, HT Y decreases
                            # Block space from (ht_end) to (gap_start)
                            block_start_y = ht_y_base_coord + ht_h_on_grid
                            block_end_y = guest_area_y_start_internal + guest_area_height_internal - ht_gap_rows_from_stage
                        
                        for y_lead in range(min(block_start_y, block_end_y), max(block_start_y, block_end_y)):
                            for c_offset in range(ht_w_on_grid):
                                x_b = ht_x_base_coord + c_offset
                                if 0 <= y_lead < actual_grid_rows and 0 <= x_b < actual_grid_cols and \
                                   (layout_grid[y_lead][x_b] is None or layout_grid[y_lead][x_b] == "BLOCKED_GAP"):
                                    layout_grid[y_lead][x_b] = "BLOCKED"
                    else: # Stage on LEFT/RIGHT
                        block_start_x, block_end_x = -1, -1
                        if stage_location == "LEFT":
                            block_start_x = guest_area_x_start_internal + ht_gap_rows_from_stage
                            block_end_x = ht_x_base_coord
                        else:
                            block_start_x = ht_x_base_coord + ht_w_on_grid
                            block_end_x = guest_area_x_start_internal + guest_area_width_internal - ht_gap_rows_from_stage
                        
                        for x_lead in range(min(block_start_x,block_end_x), max(block_start_x,block_end_x)):
                            for r_offset in range(ht_h_on_grid): # ht_h_on_grid is the "height" of HT along this axis
                                y_b = ht_y_base_coord + r_offset
                                if 0 <= y_b < actual_grid_rows and 0 <= x_lead < actual_grid_cols and \
                                   (layout_grid[y_b][x_lead] is None or layout_grid[y_b][x_lead] == "BLOCKED_GAP"):
                                    layout_grid[y_b][x_lead] = "BLOCKED"
                
                # Blocking area behind head table (further into guest seating area)
                if ht_blocks_area_behind:
                    # Iterate over each cell of the placed head table
                    for r_ht_offset in range(ht_h_on_grid):
                        for c_ht_offset in range(ht_w_on_grid):
                            ht_cell_y, ht_cell_x = ht_y_base_coord + r_ht_offset, ht_x_base_coord + c_ht_offset

                            if stage_occupies_horizontal_edge:
                                # If stage=BOTTOM (visual top), "behind" means increasing Y
                                # If stage=TOP (visual bottom), "behind" means decreasing Y
                                process_range_y = range(ht_cell_y + 1, guest_area_y_start_internal + guest_area_height_internal) if stage_location == "BOTTOM" else range(guest_area_y_start_internal, ht_cell_y)
                                for y_block in process_range_y:
                                    if 0 <= y_block < actual_grid_rows and 0 <= ht_cell_x < actual_grid_cols and \
                                       (layout_grid[y_block][ht_cell_x] is None or layout_grid[y_block][ht_cell_x] == "BLOCKED_GAP"):
                                        layout_grid[y_block][ht_cell_x] = "BLOCKED"
                            else: # Stage on LEFT/RIGHT
                                # If stage=LEFT, "behind" means increasing X
                                # If stage=RIGHT, "behind" means decreasing X
                                process_range_x = range(ht_cell_x + 1, guest_area_x_start_internal + guest_area_width_internal) if stage_location == "LEFT" else range(guest_area_x_start_internal, ht_cell_x)
                                for x_block in process_range_x:
                                    if 0 <= ht_cell_y < actual_grid_rows and 0 <= x_block < actual_grid_cols and \
                                       (layout_grid[ht_cell_y][x_block] is None or layout_grid[ht_cell_y][x_block] == "BLOCKED_GAP"):
                                        layout_grid[ht_cell_y][x_block] = "BLOCKED"
            # else: errors occurred, HT not placed or partially, skip related blocking
        # else: initial ht_row_index_in_zone or boundary checks failed.
                                
    # Manual blocking
    if manual_block_coords_str:
        try:
            manual_blocks_list_of_coords = json.loads(manual_block_coords_str)
            if isinstance(manual_blocks_list_of_coords, list):
                for item in manual_blocks_list_of_coords:
                    if isinstance(item, list) and len(item) == 2:
                        x_manual, y_manual = item[0], item[1]
                        if 0 <= y_manual < actual_grid_rows and 0 <= x_manual < actual_grid_cols:
                            if layout_grid[y_manual][x_manual] not in ["STAGE", "HEAD_TABLE"]:
                                layout_grid[y_manual][x_manual] = "BLOCKED"
                            # else: if it's STAGE or HEAD_TABLE, manual block is ignored for this cell
                        else:
                            warnings.append(f"手動阻擋座標 ({x_manual},{y_manual}) 超出場地範圍。")
            else:
                errors.append(f"手動阻擋座標格式錯誤，應為座標列表: '{manual_block_coords_str}'")
        except json.JSONDecodeError:
            errors.append(f"解析手動阻擋座標JSON時失敗: '{manual_block_coords_str}'")
        except Exception as e:
            errors.append(f"處理手動阻擋座標時發生未知錯誤: {e}")

    table_num_counter = 1
    eff_guest_x_min = guest_area_x_start_internal
    eff_guest_x_max = guest_area_x_start_internal + guest_area_width_internal
    eff_guest_y_min = guest_area_y_start_internal
    eff_guest_y_max = guest_area_y_start_internal + guest_area_height_internal
    x_coords_list = list(range(eff_guest_x_min, eff_guest_x_max))
    y_coords_list = list(range(eff_guest_y_min, eff_guest_y_max))

    # 根據舞台位置和起始角落調整迭代順序
    if stage_location == "TOP":
        if "FRONT" in numbering_start_corner: y_coords_list.reverse()
        if "RIGHT" in numbering_start_corner: x_coords_list.reverse()
    elif stage_location == "BOTTOM":
        if "BACK" in numbering_start_corner: y_coords_list.reverse()
        if "RIGHT" in numbering_start_corner: x_coords_list.reverse()
    elif stage_location == "LEFT":
        if "BACK" in numbering_start_corner: x_coords_list.reverse()
        if "RIGHT" in numbering_start_corner: y_coords_list.reverse()
    elif stage_location == "RIGHT":
        if "FRONT" in numbering_start_corner: x_coords_list.reverse()
        if "RIGHT" in numbering_start_corner: y_coords_list.reverse()

    primary_loop_is_y = False
    if stage_occupies_horizontal_edge:
        if numbering_primary_axis == "TOWARDS_STAGE_AXIS": primary_loop_is_y = True
    else:
        if numbering_primary_axis == "PARALLEL_TO_STAGE_AXIS": primary_loop_is_y = True
    
    def place_table(x_idx, y_idx):
        nonlocal table_num_counter
        if (eff_guest_y_min <= y_idx < eff_guest_y_max and
            eff_guest_x_min <= x_idx < eff_guest_x_max and
            layout_grid[y_idx][x_idx] is None):
            final_x, final_y = float(x_idx), float(y_idx)
            if stage_occupies_horizontal_edge:
                visual_col_idx = x_idx - eff_guest_x_min
                if visual_col_idx in staggered_cols_0_based:
                    final_y += 0.5
            else:
                visual_col_idx = y_idx - eff_guest_y_min
                if visual_col_idx in staggered_cols_0_based:
                    final_x += 0.5
            layout_grid[y_idx][x_idx] = f"T{table_num_counter}"
            tables_data[f"T{table_num_counter}"] = {"position": [final_x, final_y], "type": "normal", "displayName": ""}
            table_num_counter += 1

    if primary_loop_is_y:
        for y_idx in y_coords_list:
            for x_idx in x_coords_list: place_table(x_idx, y_idx)
    else:
        for x_idx in x_coords_list:
            for y_idx in y_coords_list: place_table(x_idx, y_idx)

    html = "<html><head><title>宴會廳桌位佈局</title><style>"
    html += "body { font-family: sans-serif, 'Microsoft JhengHei', 'SimSun'; display: flex; flex-direction: column; align-items: center; }"
    html += ".grid-container { display: grid; border: 1px solid #ccc; margin-bottom: 20px; }"
    html += ".grid-cell { width: 70px; height: 70px; border: 1px solid #eee; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; font-size: 11px; box-sizing: border-box; position: relative; overflow: hidden; cursor:pointer;}"
    html += ".grid-cell.manual-block-pending { background-color: #ffe0b2 !important; }"
    html += ".cell-coord { position: absolute; top: 2px; left: 2px; font-size: 8px; color: #999; }"
    html += ".STAGE { background-color: #add8e6; font-weight:bold; cursor:default !important; }"
    html += ".HEAD_TABLE { background-color: #90ee90; font-weight:bold; cursor:default !important; }"
    html += ".BLOCKED, .BLOCKED_GAP { background-color: #ffcccb; background-image: repeating-linear-gradient(45deg, transparent, transparent 5px, #f0808030 5px, #f0808030 10px); cursor:default !important; }"
    html += ".normal-table-text { font-weight: bold; font-size: 14px;}"
    html += ".params-display { margin: 20px auto; padding: 15px; border: 1px dashed #ccc; background-color: #f9f9f9; width: 80%; max-width: 680px; text-align: left;}"
    html += ".params-display h3 { margin-top: 0; text-align: center; }"
    html += ".params-display ul { list-style-type: none; padding-left: 0;}";
    html += ".params-display li { margin-bottom: 5px; }"
    html += "</style></head><body>"
    html += "<div style='width: 95%; max-width: 1000px; margin: auto; text-align:center;'>"
    html += f"<h1>宴會廳桌位佈局 (舞台位於: {params.get('stage_location', 'N/A')})</h1>"
    html += f"<h3 style='text-align:center;'>內部網格尺寸: {actual_grid_cols} 欄 x {actual_grid_rows} 排 (內部(0,0)為左下角)</h3>"
    
    html += "<form method='post' action='" + url_for('index') + "' id='manualBlockForm'>"
    for p_key, p_val in params.items():
        if p_key == 'head_table_specs' and isinstance(p_val, dict):
            if p_val.get('use_head_table'): html += f"<input type='hidden' name='use_head_table' value='yes'>"
            for ht_key, ht_val in p_val.items():
                if ht_key != 'use_head_table':
                    form_field_name = f'ht_{ht_key}'
                    if isinstance(ht_val, bool):
                        if ht_val: html += f"<input type='hidden' name='{form_field_name}' value='yes'>"
                    else: html += f"<input type='hidden' name='{form_field_name}' value='{str(ht_val)}'>"
        elif p_key == 'manual_block_coords_str': continue
        elif not isinstance(p_val, (dict, list)): html += f"<input type='hidden' name='{p_key}' value='{str(p_val)}'>"

    html += "<input type='hidden' name='manual_block_coords_str' id='manual_block_coords_input_for_submit' value='" + str(manual_block_coords_str) + "'>"
    html += "<p style='text-align:center; margin-bottom:10px;'>點擊下方賓客桌位或空白格子可標記/取消標記為「手動預留」。</p>"
    html += "<div style='text-align:center; margin-bottom:20px;'><button type='button' onclick='submitManualBlocks()' style='padding:10px 20px; font-size:1em; background-color:#007bff; color:white; border:none; border-radius:5px; cursor:pointer;'>套用手動預留並更新佈局</button></div>"
    
    html += f"<div class='grid-container' style='grid-template-columns: repeat({actual_grid_cols}, 70px); margin: 20px auto; display: inline-grid;'>"
    parsed_manual_blocks_for_highlight = set()
    try:
        initial_blocks = json.loads(manual_block_coords_str)
        if isinstance(initial_blocks, list):
            for item in initial_blocks:
                if isinstance(item, list) and len(item) == 2: parsed_manual_blocks_for_highlight.add(tuple(item))
    except: pass

    for r_internal in reversed(range(actual_grid_rows)): 
        for c_internal in range(actual_grid_cols):
            cell_content = layout_grid[r_internal][c_internal]
            cell_text, cell_class, text_span_class = "", "", ""
            cell_id_attr = f"cell_{c_internal}_{r_internal}"
            onclick_attr = ""
            is_highlighted_as_manual = (c_internal, r_internal) in parsed_manual_blocks_for_highlight

            if isinstance(cell_content, str):
                if cell_content.startswith("T"):
                    cell_text, text_span_class = cell_content, "normal-table-text"
                    onclick_attr = f"toggleManualBlock({c_internal}, {r_internal}, '{cell_id_attr}')"
                    if is_highlighted_as_manual : cell_class += " manual-block-pending"
                elif cell_content == "STAGE": cell_text, cell_class = "舞台", "STAGE"
                elif cell_content == "HEAD_TABLE": cell_text, cell_class = "主家席", "HEAD_TABLE"
                elif cell_content == "BLOCKED" or cell_content == "BLOCKED_GAP":
                    cell_text, cell_class = "預留", "BLOCKED"
                    if cell_content == "BLOCKED" and is_highlighted_as_manual:
                        onclick_attr = f"toggleManualBlock({c_internal}, {r_internal}, '{cell_id_attr}')"
                        if "manual-block-pending" not in cell_class: cell_class += " manual-block-pending"
            else: 
                onclick_attr = f"toggleManualBlock({c_internal}, {r_internal}, '{cell_id_attr}')"
                if is_highlighted_as_manual : cell_class += " manual-block-pending"
            html += f"<div id='{cell_id_attr}' class='grid-cell {cell_class.strip()}' onclick=\"{onclick_attr}\"><span class='cell-coord'>({c_internal},{r_internal})</span><span class='{text_span_class}'>{cell_text}</span></div>"
    html += "</div></form>"

    html += "<div class='params-display'><h3>本次佈局使用參數:</h3><ul>"
    param_labels = {
        "stage_location": "舞台位置", "stage_front_width_units": "舞台寬度", "stage_alignment": "舞台對齊",
        "guest_area_depth_units": "賓客區深度", "guest_area_width_units": "賓客區寬度",
        "numbering_primary_axis": "編號主軸", "numbering_start_corner": "編號起點"
    }
    param_value_maps = { 
        "stage_location": {"TOP": "上", "BOTTOM": "下", "LEFT": "左", "RIGHT": "右"},
        "stage_alignment": {"CENTER_LEAN_LEFT_BOTTOM": "中(偏左/下)", "CENTER_LEAN_RIGHT_TOP": "中(偏右/上)", "LEFT": "靠左/下", "RIGHT": "靠右/上"},
        "numbering_primary_axis": {"TOWARDS_STAGE_AXIS": "平行舞台", "PARALLEL_TO_STAGE_AXIS": "朝向舞台"},
        "numbering_start_corner": {"BACK_LEFT": "遠離舞台左側", "BACK_RIGHT": "遠離舞台右側", "FRONT_LEFT": "靠近舞台左側", "FRONT_RIGHT": "靠近舞台右側"}
    }
    for key, label in param_labels.items():
        value = params.get(key, "N/A")
        display_value = param_value_maps.get(key, {}).get(str(value), str(value))
        html += f"<li>{label}: {display_value}</li>"

    if params.get('head_table_specs') and params['head_table_specs'].get('use_head_table'):
        ht = params['head_table_specs']
        ht_align_display_val = ht.get('alignment', 'N/A')
        ht_align_display = param_value_maps.get("stage_alignment", {}).get(str(ht_align_display_val), str(ht_align_display_val))
        html += f"<li>主家席: 已啟用<ul><li>間隔: {ht.get('gap_rows_from_stage', 'N/A')}排</li><li>於間隔區/後第: {ht.get('row_index_in_zone', 'N/A')}排</li><li>寬x深: {ht.get('width_units', 'N/A')}x{ht.get('depth_units', 'N/A')}</li><li>對齊: {ht_align_display}</li><li>阻擋前方空間: {'是' if ht.get('block_leading_space', False) else '否'}</li><li>阻擋後方空間: {'是' if ht.get('blocks_area_behind', False) else '否'}</li></ul></li>"
    else: html += "<li>主家席: 未啟用</li>"
    html += f"<li>手動阻擋: {params.get('manual_block_coords_str', '[]')}</li></ul></div>"
    html += f"<h2 style='text-align:center;'>JSON 數據:</h2><pre style='background-color: #f0f0f0; padding:10px; border-radius:5px; white-space: pre-wrap; word-wrap: break-word; margin: 0 auto; width: 80%; max-width: 680px;'>{json.dumps(tables_data, indent=4, ensure_ascii=False)}</pre>"
    html += """
        <script>
            let manuallyAppliedBlockCoords = new Set(); 
            function initializePreviewManualBlocks() {
                const currentBlocksStr = document.getElementById('manual_block_coords_input_for_submit').value;
                manuallyAppliedBlockCoords = new Set();
                if (currentBlocksStr && currentBlocksStr !== "[]") {
                    try {
                        const currentBlocks = JSON.parse(currentBlocksStr); 
                        currentBlocks.forEach(coordPair => {
                            if (Array.isArray(coordPair) && coordPair.length === 2) {
                                const coordStr = coordPair[0] + "_" + coordPair[1];
                                manuallyAppliedBlockCoords.add(coordStr);
                                const cellElement = document.getElementById('cell_' + coordPair[0] + '_' + coordPair[1]);
                                if (cellElement && !cellElement.classList.contains('STAGE') && !cellElement.classList.contains('HEAD_TABLE')) {
                                    if (cellElement.classList.contains('BLOCKED') && cellElement.getAttribute('onclick') && cellElement.getAttribute('onclick').includes('toggleManualBlock')) {
                                        cellElement.classList.add('manual-block-pending');
                                    } else if (!cellElement.classList.contains('BLOCKED')) {
                                        cellElement.classList.add('manual-block-pending');
                                    }
                                }
                            }
                        });
                    } catch (e) { console.error("Error parsing initial manual blocks for preview:", e); }
                }
            }
            function toggleManualBlock(x, y, cellId) {
                const coordStr = x + "_" + y;
                const cellElement = document.getElementById(cellId);
                if (!cellElement || cellElement.classList.contains('STAGE') || cellElement.classList.contains('HEAD_TABLE')) return; 
                if (cellElement.classList.contains('BLOCKED') && !cellElement.classList.contains('manual-block-pending')) return;
                if (manuallyAppliedBlockCoords.has(coordStr)) {
                    manuallyAppliedBlockCoords.delete(coordStr);
                    cellElement.classList.remove('manual-block-pending');
                } else {
                    manuallyAppliedBlockCoords.add(coordStr);
                    cellElement.classList.add('manual-block-pending');
                }
                const coordsArray = Array.from(manuallyAppliedBlockCoords).map(s => s.split('_').map(Number));
                document.getElementById('manual_block_coords_input_for_submit').value = JSON.stringify(coordsArray);
            }
            function submitManualBlocks() {
                const coordsArray = Array.from(manuallyAppliedBlockCoords).map(s => s.split('_').map(Number));
                document.getElementById('manual_block_coords_input_for_submit').value = JSON.stringify(coordsArray);
                document.getElementById('manualBlockForm').submit();
            }
            document.addEventListener('DOMContentLoaded', () => {
                if (document.querySelector('.grid-container') && document.getElementById('manual_block_coords_input_for_submit')) {
                    initializePreviewManualBlocks();
                }
            });
        </script>
    """
    html += "</div></body></html>"

    if not isinstance(html, str) or not html.strip():
        if app.debug: app.logger.error("generate_layout_data 未能產生有效的HTML。")
        return "<p>錯誤: 預覽HTML內容生成失敗。</p>", {}

    try:
        base_dir = os.path.abspath(os.path.dirname(__file__))
        json_file_path = os.path.join(base_dir, "table_locations.json")
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(tables_data, f, ensure_ascii=False, indent=4)
    except IOError as e:
        if app.debug: app.logger.warning(f"寫入 table_locations.json 失敗: {e}")
    return html, tables_data

# --- Flask App 設定 ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- Flask 路由和附加邏輯 ---
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
        input[type="number"], select, textarea { width: 100%; padding: 12px; margin-top: 5px; border: 1px solid #ced4da; border-radius: 6px; box-sizing: border-box; font-size: 1em; transition: border-color 0.3s; }
        input[type="number"]:focus, select:focus, textarea:focus { border-color: #007bff; outline: none; box-shadow: 0 0 0 0.2rem rgba(0,123,255,.25); }
        .button-group { margin-top: 30px; display: flex; justify-content: space-around; align-items:center; flex-wrap: wrap; } /* Added space-around and wrap */
        .button-group button, .button-group input[type="submit"] { padding: 10px 15px; margin: 5px; border: none; border-radius: 6px; cursor: pointer; font-size: 1em; font-weight: 500; transition: background-color 0.3s, transform 0.1s; flex-grow: 1; min-width: 180px; } /* Adjusted padding and added flex properties */
        input[type="submit"][name="action_generate_new_clear_blocks"] { background-color: #dc3545; color: white; } /* Red for clear */
        input[type="submit"][name="action_generate_new_clear_blocks"]:hover { background-color: #c82333; }
        input[type="submit"][name="action_generate_update_keep_blocks"] { background-color: #28a745; color: white; } /* Green for update/keep */
        input[type="submit"][name="action_generate_update_keep_blocks"]:hover { background-color: #218838; }
        button[type="button"] { background-color: #ffc107; color: #212529; } /* Yellow for reset */
        button[type="button"]:hover { background-color: #e0a800; }
        .checkbox-label { display: inline-block; margin-left: 8px; font-weight: normal; vertical-align: middle; }
        input[type="checkbox"] { vertical-align: middle; width: auto; margin-right: 0;}
        .form-section { margin-bottom: 25px; padding: 20px; background-color: #fdfdfd; border: 1px solid #e9ecef; border-radius: 8px; }
        .message { padding: 10px; border-radius: 6px; margin-top: 15px; font-size: 0.95em; text-align:center; }
        .error { color: #721c24; background-color: #f8d7da; border: 1px solid #f5c6cb;}
        .success { color: #155724; background-color: #d4edda; border: 1px solid #c3e6cb;}
        .info { color: #004085; background-color: #cce5ff; border: 1px solid #b8daff;}
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

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="message {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <form method="post" id="layoutForm">
            <h2>請填寫以下參數產生佈局</h2>
            <div class="form-section">
                <h2>舞台設定</h2>
                <label for="stage_location">舞台位置:</label>
                <select name="stage_location" id="stage_location">
                    <option value="TOP" {% if form_data.stage_location == "TOP" %}selected{% endif %}>最上方 (遠端)</option>
                    <option value="BOTTOM" {% if form_data.stage_location == "BOTTOM" %}selected{% endif %}>最下方 (近端)</option>
                    <option value="LEFT" {% if form_data.stage_location == "LEFT" %}selected{% endif %}>最左邊</option>
                    <option value="RIGHT" {% if form_data.stage_location == "RIGHT" %}selected{% endif %}>最右邊</option>
                </select>
                <label for="stage_front_width_units">舞台寬度 (單位):</label>
                <input type="number" name="stage_front_width_units" id="stage_front_width_units" value="{{ form_data.stage_front_width_units }}" min="1">
                <label for="stage_alignment">舞台對齊:</label>
                <select name="stage_alignment" id="stage_alignment">
                    <option value="CENTER_LEAN_LEFT_BOTTOM" {% if form_data.stage_alignment == "CENTER_LEAN_LEFT_BOTTOM" %}selected{% endif %}>置中 (偏左/下)</option>
                    <option value="CENTER_LEAN_RIGHT_TOP" {% if form_data.stage_alignment == "CENTER_LEAN_RIGHT_TOP" %}selected{% endif %}>置中 (偏右/上)</option>
                    <option value="LEFT" {% if form_data.stage_alignment == "LEFT" %}selected{% endif %}>靠左/下</option>
                    <option value="RIGHT" {% if form_data.stage_alignment == "RIGHT" %}selected{% endif %}>靠右/上</option>
                </select>
            </div>

            <div class="form-section">
                <h2>賓客區設定</h2>
                <label for="guest_area_depth_units">賓客區深度 (排數):</label>
                <input type="number" name="guest_area_depth_units" id="guest_area_depth_units" value="{{ form_data.guest_area_depth_units }}" min="1">
                <label for="guest_area_width_units">賓客區寬度 (每排桌數):</label>
                <input type="number" name="guest_area_width_units" id="guest_area_width_units" value="{{ form_data.guest_area_width_units }}" min="1">
                <label for="stagger-controls-container">交錯直行設定:</label>
                <div id="stagger-controls-container">
                    </div>
                <input type="hidden" name="staggered_columns_str" id="staggered_columns_str" value='{{ form_data.staggered_columns_str }}'>
            </div>
            </div>

            <div class="form-section">
                <h2>桌號編排</h2>
                <label for="numbering_primary_axis">主要編號軸向:</label>
                <select name="numbering_primary_axis" id="numbering_primary_axis">
                    <option value="TOWARDS_STAGE_AXIS" {% if form_data.numbering_primary_axis == "TOWARDS_STAGE_AXIS" %}selected{% endif %}>沿「平行舞台」</option>
                    <option value="PARALLEL_TO_STAGE_AXIS" {% if form_data.numbering_primary_axis == "PARALLEL_TO_STAGE_AXIS" %}selected{% endif %}>沿「朝向舞台」</option>
                </select>
                <label for="numbering_start_corner">編號起始角落:</label>
                <select name="numbering_start_corner" id="numbering_start_corner">
                    <option value="BACK_LEFT" {% if form_data.numbering_start_corner == "BACK_LEFT" %}selected{% endif %}>遠離舞台左側</option>
                    <option value="BACK_RIGHT" {% if form_data.numbering_start_corner == "BACK_RIGHT" %}selected{% endif %}>遠離舞台右側</option>
                    <option value="FRONT_LEFT" {% if form_data.numbering_start_corner == "FRONT_LEFT" %}selected{% endif %}>靠近舞台左側</option>
                    <option value="FRONT_RIGHT" {% if form_data.numbering_start_corner == "FRONT_RIGHT" %}selected{% endif %}>靠近舞台右側</option>
                </select>
            </div>
            
            <div class="form-section">
                <h2>(可選) 主家席</h2>
                <input type="checkbox" name="use_head_table" id="use_head_table" value="yes" {% if form_data.use_head_table %}checked{% endif %} onchange="toggleHeadTableOptions()">
                <label for="use_head_table" class="checkbox-label">啟用主家席</label>
                <div id="head_table_options" class="sub-options {% if form_data.use_head_table %}active{% endif %}">
                    <label for="ht_gap_rows_from_stage">與舞台間隔排數:</label>
                    <input type="number" name="ht_gap_rows_from_stage" id="ht_gap_rows_from_stage" value="{{ form_data.ht_gap_rows_from_stage }}" min="0">
                    <label for="ht_row_index_in_zone">於間隔區/後第幾排:</label>
                    <input type="number" name="ht_row_index_in_zone" id="ht_row_index_in_zone" value="{{ form_data.ht_row_index_in_zone }}">
                    <input type="checkbox" name="ht_block_leading_space" id="ht_block_leading_space" value="yes" {% if form_data.ht_block_leading_space %}checked{% endif %}>
                    <label for="ht_block_leading_space" class="checkbox-label">阻擋主家席與間隔間額外空間</label><br>
                    <label for="ht_width_units" style="margin-top:10px;">主家席寬度:</label>
                    <input type="number" name="ht_width_units" id="ht_width_units" value="{{ form_data.ht_width_units }}" min="1">
                    <label for="ht_depth_units">主家席深度:</label>
                    <input type="number" name="ht_depth_units" id="ht_depth_units" value="{{ form_data.ht_depth_units }}" min="1">
                    <label for="ht_alignment">主家席對齊:</label>
                    <select name="ht_alignment" id="ht_alignment">
                        <option value="CENTER_LEAN_LEFT_BOTTOM" {% if form_data.ht_alignment == "CENTER_LEAN_LEFT_BOTTOM" %}selected{% endif %}>置中 (偏左/下)</option>
                        <option value="CENTER_LEAN_RIGHT_TOP" {% if form_data.ht_alignment == "CENTER_LEAN_RIGHT_TOP" %}selected{% endif %}>置中 (偏右/上)</option>
                        <option value="ALIGN_LEFT" {% if form_data.ht_alignment == "ALIGN_LEFT" %}selected{% endif %}>靠左/下</option>
                        <option value="ALIGN_RIGHT" {% if form_data.ht_alignment == "ALIGN_RIGHT" %}selected{% endif %}>靠右/上</option>
                    </select><br>
                    <input type="checkbox" name="blocks_area_behind" id="blocks_area_behind" value="yes" {% if form_data.blocks_area_behind %}checked{% endif %} style="margin-top:10px;">
                    <label for="blocks_area_behind" class="checkbox-label">阻擋其後方桌位</label>
                </div>
            </div>
            <div class="form-section">
                <h2>(可選) 手動預留</h2>
                <label for="manual_block_coords_input_form">手動預留座標 (JSON字串, 例: [[0,0],[1,0]] ):</label>
                <textarea name="manual_block_coords_str" id="manual_block_coords_input_form" rows="2" placeholder="例如: [[0,0], [1,0]]">{{ form_data.manual_block_coords_str | default('[]') }}</textarea>
            </div>

            <div class="button-group">
                <button type="button" onclick="resetToDefaults()">恢復預設值</button>
                <input type="submit" name="action_generate_update_keep_blocks" value="更新佈局 (保留預留)">
                <input type="submit" name="action_generate_new_clear_blocks" value="產生新佈局 (清除預留)">
            </div>
        </form>
        <script>
            const defaultValues = {{ default_values_json | safe }};
            function toggleHeadTableOptions() {
                const useHtCheckbox = document.getElementById('use_head_table');
                const htOptionsDiv = document.getElementById('head_table_options');
                if (useHtCheckbox.checked) { htOptionsDiv.classList.add('active'); } 
                else { htOptionsDiv.classList.remove('active'); }
            }
            function resetToDefaults() {
                if (confirm("確定要將所有參數恢復為預設值嗎？手動預留的格子也將被清除。")) {
                    for (const key in defaultValues) {
                        const element = document.getElementById(key) || document.getElementsByName(key)[0];
                        if (element) {
                            if (element.type === 'checkbox') { element.checked = defaultValues[key]; } 
                            else { element.value = defaultValues[key]; }
                        }
                    }
                    document.getElementById('manual_block_coords_input_form').value = defaultValues['manual_block_coords_str'] || "[]";
                    toggleHeadTableOptions();
                }
            }
            function updateStaggerControls() {
                const widthInput = document.getElementById('guest_area_width_units');
                const container = document.getElementById('stagger-controls-container');
                const hiddenInput = document.getElementById('staggered_columns_str');
                if (!widthInput || !container || !hiddenInput) return;

                const width = parseInt(widthInput.value, 10) || 0;
                container.innerHTML = '';
                let selected = [];
                try {
                    selected = JSON.parse(hiddenInput.value || '[]');
                } catch (e) { selected = []; }
                
                if (width > 0 && width < 101) { // Safety limit
                    for (let i = 1; i <= width; i++) {
                        const label = document.createElement('label');
                        const checkbox = document.createElement('input');
                        checkbox.type = 'checkbox';
                        checkbox.dataset.column = i;
                        if (selected.includes(i)) checkbox.checked = true;
                        label.appendChild(checkbox);
                        label.appendChild(document.createTextNode(` ${i} `));
                        container.appendChild(label);
                    }
                }
            }
            
            function collectStaggerSettings() {
                const container = document.getElementById('stagger-controls-container');
                const hiddenInput = document.getElementById('staggered_columns_str');
                if (!container || !hiddenInput) return;
                const selected = [];
                container.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
                    selected.push(parseInt(cb.dataset.column, 10));
                });
                hiddenInput.value = JSON.stringify(selected);
            }

            document.addEventListener('DOMContentLoaded', () => {
                toggleHeadTableOptions();
                updateStaggerControls(); // Initial call
                
                const widthInput = document.getElementById('guest_area_width_units');
                const container = document.getElementById('stagger-controls-container');

                if (widthInput) {
                    widthInput.addEventListener('change', updateStaggerControls);
                    widthInput.addEventListener('keyup', updateStaggerControls);
                }
                if (container) {
                    container.addEventListener('change', collectStaggerSettings);
                }
                const form = document.getElementById('layoutForm');
                if (form) {
                    form.addEventListener('submit', collectStaggerSettings);
                }
            });
        </script>
    </div>
    </div>
</body>
</html>
"""

DEFAULT_FORM_VALUES = {
    "stage_location": "TOP", "stage_front_width_units": 4, "stage_alignment": "CENTER_LEAN_LEFT_BOTTOM",
    "guest_area_depth_units": 8, "guest_area_width_units": 5,
    "numbering_primary_axis": "TOWARDS_STAGE_AXIS", "numbering_start_corner": "BACK_LEFT",
    "use_head_table": False, "ht_gap_rows_from_stage": 0, "ht_row_index_in_zone": 1,
    "ht_block_leading_space": False, "ht_width_units": 2, "ht_depth_units": 1,
    "ht_alignment": "CENTER_LEAN_LEFT_BOTTOM", "blocks_area_behind": False, 
    "manual_block_coords_str": "[]",
    "staggered_columns_str": "[]"
}

def safe_int(value, default=0):
    if value is None: return default
    try: return int(value)
    except (ValueError, TypeError):
        try: return int(default)
        except: return 0

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        current_form_data_from_html = request.form.to_dict(flat=True)
        session['form_data'] = current_form_data_from_html.copy() 

        try:
            params = {
                "stage_location": current_form_data_from_html.get('stage_location', DEFAULT_FORM_VALUES['stage_location']),
                "stage_front_width_units": safe_int(current_form_data_from_html.get('stage_front_width_units'), DEFAULT_FORM_VALUES['stage_front_width_units']),
                "stage_alignment": current_form_data_from_html.get('stage_alignment', DEFAULT_FORM_VALUES['stage_alignment']),
                "guest_area_depth_units": safe_int(current_form_data_from_html.get('guest_area_depth_units'), DEFAULT_FORM_VALUES['guest_area_depth_units']),
                "guest_area_width_units": safe_int(current_form_data_from_html.get('guest_area_width_units'), DEFAULT_FORM_VALUES['guest_area_width_units']),
                "numbering_primary_axis": current_form_data_from_html.get('numbering_primary_axis', DEFAULT_FORM_VALUES['numbering_primary_axis']),
                "numbering_start_corner": current_form_data_from_html.get('numbering_start_corner', DEFAULT_FORM_VALUES['numbering_start_corner']),
                "head_table_specs": None,
                "staggered_columns_str": current_form_data_from_html.get('staggered_columns_str', DEFAULT_FORM_VALUES['staggered_columns_str'],)
            }

            if 'action_generate_new_clear_blocks' in current_form_data_from_html:
                params["manual_block_coords_str"] = "[]"
                session['form_data']['manual_block_coords_str'] = "[]" 
            elif 'action_generate_update_keep_blocks' in current_form_data_from_html:
                params["manual_block_coords_str"] = current_form_data_from_html.get('manual_block_coords_str', DEFAULT_FORM_VALUES['manual_block_coords_str'])
            else: # From preview page or Enter key submission
                params["manual_block_coords_str"] = current_form_data_from_html.get('manual_block_coords_str', DEFAULT_FORM_VALUES['manual_block_coords_str'])

            if 'use_head_table' in current_form_data_from_html:
                params["head_table_specs"] = {
                    "use_head_table": True,
                    "gap_rows_from_stage": safe_int(current_form_data_from_html.get('ht_gap_rows_from_stage'), DEFAULT_FORM_VALUES['ht_gap_rows_from_stage']),
                    "row_index_in_zone": safe_int(current_form_data_from_html.get('ht_row_index_in_zone'), DEFAULT_FORM_VALUES['ht_row_index_in_zone']),
                    "block_leading_space": 'ht_block_leading_space' in current_form_data_from_html,
                    "width_units": safe_int(current_form_data_from_html.get('ht_width_units'), DEFAULT_FORM_VALUES['ht_width_units']),
                    "depth_units": safe_int(current_form_data_from_html.get('ht_depth_units'), DEFAULT_FORM_VALUES['ht_depth_units']),
                    "alignment": current_form_data_from_html.get('ht_alignment', DEFAULT_FORM_VALUES['ht_alignment']),
                    "blocks_area_behind": 'blocks_area_behind' in current_form_data_from_html
                }
                ht = params["head_table_specs"]
                if ht["width_units"] < 1 or ht["depth_units"] < 1 or ht["gap_rows_from_stage"] < 0:
                    flash("提醒: 主家席參數可能無效。", "info")
            
            if params["stage_front_width_units"] < 1 or params["guest_area_depth_units"] < 1 or params["guest_area_width_units"] < 1:
                flash("提醒: 舞台或賓客區尺寸需至少為1。", "info")
            
            # (Non-blocking width validation info messages can be kept if desired)

            html_preview_content, _ = generate_layout_data(params)
            
            if app.debug:
                app.logger.debug(f"HTML Preview Type: {type(html_preview_content)}, Length: {len(html_preview_content) if isinstance(html_preview_content, str) else 'N/A'}")

            if not html_preview_content or not isinstance(html_preview_content, str) or not html_preview_content.strip():
                flash('產生佈局預覽失敗。', 'error')
            else:
                try:
                    base_dir = os.path.abspath(os.path.dirname(__file__))
                    preview_file_path = os.path.join(base_dir, "temp_preview.html")
                    with open(preview_file_path, "w", encoding="utf-8") as f_preview:
                        f_preview.write(html_preview_content)
                    session['has_preview_file'] = True 
                    if app.debug: app.logger.debug(f"預覽HTML已寫入: {preview_file_path}")
                    flash('成功產生佈局！', 'success')
                    return redirect(url_for('show_preview'))
                except IOError as e:
                    if app.debug: app.logger.error(f"寫入暫存預覽檔失敗: {e}")
                    flash("產生預覽時無法寫入暫存檔。", "error")
        
        except ValueError as e: flash(f'參數數值錯誤: {str(e)}', 'error')
        except KeyError as e: flash(f'缺少參數: {str(e)}。', 'error')
        except Exception as e:
            if app.debug: app.logger.error(f"產生佈局時發生未預期錯誤: {e}", exc_info=True)
            flash(f"產生佈局時發生錯誤 ({type(e).__name__})。", 'error')
        
    form_data_for_template = {}
    source_data_for_form = session.get('form_data', DEFAULT_FORM_VALUES.copy())
    for key, default_value in DEFAULT_FORM_VALUES.items():
        value_from_source = source_data_for_form.get(key)
        if value_from_source is None: form_data_for_template[key] = default_value
        elif isinstance(default_value, bool): form_data_for_template[key] = str(value_from_source).lower() in ['true', 'yes', 'on']
        elif isinstance(default_value, int): form_data_for_template[key] = safe_int(value_from_source, default_value)
        else: form_data_for_template[key] = str(value_from_source)
    return render_template_string(HTML_FORM_TEMPLATE, form_data=form_data_for_template, default_values_json=json.dumps(DEFAULT_FORM_VALUES))

@app.route('/preview')
def show_preview():
    if session.get('has_preview_file'):
        try:
            base_dir = os.path.abspath(os.path.dirname(__file__))
            preview_file_path = os.path.join(base_dir, "temp_preview.html")
            if app.debug: app.logger.debug(f"嘗試讀取預覽: {preview_file_path}")
            if os.path.exists(preview_file_path):
                with open(preview_file_path, "r", encoding="utf-8") as f_preview: content = f_preview.read()
                if app.debug: app.logger.debug(f"成功讀取預覽檔. 長度: {len(content)}")
                preview_styles = "<style>.preview-actions a{padding:8px 12px;background-color:#007bff;color:white;text-decoration:none;border-radius:5px;display:inline-block;margin:5px}.preview-actions a:hover{background-color:#0056b3}</style>"
                actions = f"<p class='preview-actions'><a href='{url_for('download_json')}'>下載JSON</a> <a href='{url_for('index')}'>返回修改</a></p>"
                return preview_styles + f"<div style='width:95%;max-width:1200px;margin:20px auto;text-align:center'>{actions}{content}{actions}</div>"
            else:
                if app.debug: app.logger.error(f"預覽檔未找到: {preview_file_path}")
                flash("預覽文件遺失，請重新產生。", "error")
                session.pop('has_preview_file', None)
        except IOError as e:
            if app.debug: app.logger.error(f"讀取預覽檔錯誤: {e}")
            flash("讀取預覽時發生內部錯誤。", "error")
            session.pop('has_preview_file', None)
    else:
        if app.debug: app.logger.debug("Session中無 'has_preview_file'，重定向到index。")
        flash("沒有可預覽的佈局。請先產生一個。", "info")
    return redirect(url_for('index'))

@app.route('/download_json')
def download_json():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    json_path = os.path.join(base_dir, "table_locations.json")
    if os.path.exists(json_path):
        return send_file(json_path, as_attachment=True, download_name="table_locations.json", mimetype='application/json')
    flash("JSON 檔案不存在。", "error")
    return redirect(url_for('index'))

if __name__ == '__main__':
    base_dir = os.path.abspath(os.path.dirname(__file__))
    temp_preview_file = os.path.join(base_dir, "temp_preview.html")
    if os.path.exists(temp_preview_file):
        try:
            os.remove(temp_preview_file)
            print(f"已清理舊預覽: {temp_preview_file}")
        except OSError as e: print(f"清理舊預覽失敗: {e}")
    print("啟動宴會廳桌位佈局產生器於 http://127.0.0.1:5000/")
    app.run(host="0.0.0.0", port=5000, debug=True)