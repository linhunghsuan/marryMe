def generate_table_layout_html_v3(total_tables, cols, rows, main_table_size, main_table_alignment, main_table_start_offset=None, origin='bottom-left'):
    """
    產生包含桌位編號和座標的 HTML 頁面 (更精細的佈局控制)。
    """
    if cols * rows < total_tables:
        return "<p>警告：指定的行列數不足以容納所有桌位。</p>"

    main_table_width, main_table_height = main_table_size
    main_table_col_start, main_table_row_start = -1, -1

    if main_table_alignment:
        # ... (與 v2 相同，計算 main_table_col_start, main_table_row_start) ...
        if main_table_alignment == 'bottom':
            main_table_row_start = 0
            main_table_col_start = (cols - main_table_width) // 2
        elif main_table_alignment == 'top':
            main_table_row_start = rows - main_table_height
            main_table_col_start = (cols - main_table_width) // 2
        elif main_table_alignment == 'left':
            main_table_col_start = 0
            main_table_row_start = (rows - main_table_height) // 2
        elif main_table_alignment == 'right':
            main_table_col_start = cols - main_table_width
            main_table_row_start = (rows - main_table_height) // 2
    elif main_table_start_offset:
        main_table_col_start, main_table_row_start = main_table_start_offset

    # 創建佈局網格
    grid_width = cols + (main_table_width - 1 if main_table_col_start != -1 else 0)
    grid_height = rows + (main_table_height - 1 if main_table_row_start != -1 else 0)
    layout_grid = [[None for _ in range(grid_width)] for _ in range(grid_height)]

    # 標記主桌
    if main_table_col_start != -1:
        for r in range(main_table_row_start, main_table_row_start + main_table_height):
            for c in range(main_table_col_start, main_table_col_start + main_table_width):
                # 需要根據 origin 調整這裡的網格索引
                grid_x, grid_y = c, r
                if origin == 'top-left':
                    grid_y = rows - 1 - r
                elif origin == 'bottom-right':
                    grid_x = cols - 1 - c
                elif origin == 'top-right':
                    grid_x = cols - 1 - c
                    grid_y = rows - 1 - r

                try:
                    layout_grid[grid_y][grid_x] = {"type": "main"}
                except IndexError:
                    print(f"主桌位置超出網格範圍: ({grid_x}, {grid_y})")

    tables = {}
    table_counter = 1
    for r in range(rows):
        for c in range(cols):
            if table_counter <= total_tables:
                tables[(c, r)] = {"id": f"T{table_counter}", "original_grid": (c, r)}
                table_counter += 1
            else:
                break
        if table_counter > total_tables:
            break

    placed_tables = {}
    table_index = 1

    # 垂直方向放置桌位
    for gc in range(grid_width):
        for gr in range(grid_height):
            if table_index > total_tables:
                break
            if layout_grid[gr][gc] is None:
                # 找到對應編號的原始桌位資訊
                original_table = next((t for coord, t in tables.items() if t["id"] == f"T{table_index}"), None)
                if original_table:
                    placed_tables[original_table["id"]] = {"position": (gc, gr), "original": original_table["original_grid"]}
                    layout_grid[gr][gc] = {"type": "normal", "id": original_table["id"]}
                    table_index += 1
        if table_index > total_tables:
            break

    html_output = "<h1>桌位佈局 (v3)</h1>\n"
    html_output += "<p>總桌位數: {}</p>\n".format(total_tables)
    html_output += "<p>網格大小: {}x{}</p>\n".format(cols, rows)
    if main_table_col_start != -1:
        alignment_str = f"靠 {main_table_alignment}" if main_table_alignment else f"起始於 ({main_table_col_start}, {main_table_row_start})"
        html_output += f"<p>主桌大小: {main_table_size[0]}x{main_table_size[1]}, 位置: {alignment_str}</p>\n"
    html_output += "<p>原點方向: {}</p>\n".format(origin)
    html_output += "<hr>\n"
    html_output += f"<div style='display: grid; grid-template-columns: repeat({grid_width}, 50px); grid-auto-rows: 50px; gap: 5px;'>\n"

    for gr in range(grid_height):
        for gc in range(grid_width):
            cell = layout_grid[gr][gc]
            if cell:
                style = "border: 1px solid black; display: flex; justify-content: center; align-items: center;"
                text = ""
                if cell["type"] == "main":
                    style += " background-color: lightblue;"
                    text = "(主桌)"
                elif cell["type"] == "normal":
                    text = f"{cell['id']}<br>({gc}, {gr})"
                html_output += f"<div style='grid-column: {gc + 1}; grid-row: {gr + 1}; {style}'>{text}</div>\n"
            else:
                html_output += "<div></div>\n" # 空白格

    html_output += "</div>\n"
    html_output += "<hr>\n"
    html_output += "<h2>桌位編號與實際位置對應</h2>\n"
    html_output += "<ul>\n"
    for table_id, info in sorted(placed_tables.items(), key=lambda item: int(item[0][1:])):
        html_output += f"<li>{table_id}: 顯示位置 ({info['position'][0]}, {info['position'][1]}), 原始網格 ({info['original'][0]}, {info['original'][1]})</li>\n"
    html_output += "</ul>\n"
    html_output += "<p>請在客人清單中填寫<b>桌位編號</b> (例如: T1, T2...) 來指定客人的位置。</p>"

    return f"""<!DOCTYPE html><html><head><title>桌位佈局 (v3)</title><style>body {{ font-family: sans-serif; }}.grid-container {{display: grid;gap: 5px;border: 1px solid #ccc;padding: 10px;}}.grid-item {{border: 1px solid #eee;padding: 10px;text-align: center;}}.main-table {{background-color: lightblue;}}</style></head><body>{html_output}</body></html>"""

if __name__ == '__main__':
    total_tables = 32
    cols = 5
    rows = 7
    main_table_size = (2, 2)
    main_table_alignment = 'right'
    main_table_start_offset = None
    origin = 'bottom-right'

    html_content = generate_table_layout_html_v3(total_tables, cols, rows, main_table_size, main_table_alignment, main_table_start_offset, origin)

    with open("table_layout.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print("已生成 table_layout.html")

    html_content_bottom = generate_table_layout_html_v3(total_tables, cols, rows, (2, 2), 'bottom', None, 'bottom-left')
    with open("table_layout_bottom.html", "w", encoding="utf-8") as f:
        f.write(html_content_bottom)
    print("已生成 table_layout_bottom.html")