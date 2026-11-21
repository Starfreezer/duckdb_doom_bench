import time
import random
import statistics as stats

import duckdb 



NUM_TEXTURES = 50
NUM_SAMPLES = 20000

TEX_WIDTH = 64
TEX_HEIGHT = 128

FLATS_WIDTH = 64
FLATS_HEIGHT = 64

SPRITE_WIDTH = 64
SPRITE_HEIGHT = 64

NUM_WARMUP_RUNS = 50
NUM_RUNS = 500


def __create_texture_lists_helper (id: int) -> list[int]:
    texture = []
    random.seed(id)
    for _ in range(TEX_WIDTH * TEX_HEIGHT):
        texture.append(random.randint(0,255))

    assert len(texture) == TEX_WIDTH * TEX_HEIGHT
    return texture



def create_texture_lists() -> dict[int, list[int]]:
    print("Creating texture lists")
    textures = {}
    for i in range(NUM_TEXTURES):
        textures[i] = __create_texture_lists_helper(i)

    assert len(textures) == NUM_TEXTURES
    return textures

def sample_coordinates_wall(i: int):
    texture_id = (i // (TEX_WIDTH* TEX_HEIGHT)) % NUM_TEXTURES

    u = (i // TEX_HEIGHT) % TEX_WIDTH
    v = i % TEX_HEIGHT 

    return texture_id, u, v


def main():
    print(f"DuckDB version: {duckdb.__version__}")

    # Keep the benchmark deterministic and single-threaded initially.
    con = duckdb.connect(
        ":memory:",
        config={"threads": 1},
    )

    ### Texture stored as large list in row major order
    con.execute("""
        CREATE TABLE textures_list (
            texture_id INTEGER PRIMARY KEY,
            width      INTEGER NOT NULL,
            height     INTEGER NOT NULL,
            pixels     UTINYINT[] NOT NULL
        )
    """)

    texture_lists = create_texture_lists()

    print("Inserting textures")
    for tex_id,tex_pixels in texture_lists.items():
        con.execute(
                """
                INSERT INTO textures_list
                VALUES(?,?,?,?)
                """,
                [tex_id,TEX_WIDTH,TEX_HEIGHT,tex_pixels]
                )

    print("Sampling textures")
    con.execute(f"""
        CREATE TABLE samples AS 
        SELECT v.i AS sample_id,

        CAST(floor(v.i/ {TEX_WIDTH * TEX_HEIGHT})
        % {NUM_TEXTURES} AS INTEGER) AS texture_id,

        CAST(floor(i/{TEX_HEIGHT}) % {TEX_WIDTH} AS INTEGER) AS u,

        CAST(i % {TEX_HEIGHT} AS INTEGER) AS v

        FROM generate_series(0,{NUM_SAMPLES - 1}) v(i)

            """)

    print("Calculating sql checksum")
    sample_walls_sql = """
        SELECT SUM(l.pixels[(s.v * l.width) + s.u + 1]) AS checksum
        FROM textures_list AS l 
        JOIN samples AS s 
        ON s.texture_id = l.texture_id
    """

    sample_walls_scan_only = """
        SELECT SUM(s.u + s.v) AS res
        FROM samples AS s 
    """

    sample_walls_join_only = """
        SELECT SUM(s.u + s.v + l.width) AS res 
        FROM textures_list AS l 
        JOIN samples AS s 
        ON s.texture_id = l.texture_id
    """

    checksum_duckdb = con.sql(sample_walls_sql).fetchall()[0][0]
    checksum_python = 0

    print("Calculating python checksum")
    for i in range(NUM_SAMPLES):
        texture_id, u, v = sample_coordinates_wall(i)
        offset = v * TEX_WIDTH + u 
        checksum_python+= texture_lists[texture_id][offset]

    print(f"checksum duckdb {checksum_duckdb}")
    print(f"checksum python {checksum_python}")

    assert checksum_python == checksum_duckdb
    print("Checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(sample_walls_sql).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"Warmup time elapsed {warmup_end - warmup_start} seconds")


    print()
    print("####################################################################################################")
    print("Beginning benchmark for wall like acesses") 

    wall_like_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter() 
        con.sql(sample_walls_sql).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    wall_like_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} wall like acesses: {wall_like_end - wall_like_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")

    print()
    print("####################################################################################################")
    print("Beginn benchmark for wall like acesses SCAN ONLY")
    wall_like_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter() 
        con.sql(sample_walls_scan_only).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    wall_like_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} wall like acesses SCAN ONLY: {wall_like_end - wall_like_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")

    print()
    print("####################################################################################################")
    print("Begin Benchmark for wall like acesses JOINS only")
    wall_like_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter() 
        con.sql(sample_walls_join_only).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    wall_like_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} wall like acesses JOIN ONLY: {wall_like_end - wall_like_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")

    ### Texture stored as large list in column major order
    con.execute("""
        CREATE TABLE textures_list_column_major (
            texture_id INTEGER PRIMARY KEY,
            width      INTEGER NOT NULL,
            height     INTEGER NOT NULL,
            pixels     UTINYINT[] NOT NULL
        )
    """)

    print()
    print("Creating column major texture lists")
    texture_lists_column_major = {}
    for tex_id,tex_pixels in texture_lists.items():
        column_major_pixels = []
        for u in range(TEX_WIDTH):
            for v in range(TEX_HEIGHT):
                column_major_pixels.append(tex_pixels[(v * TEX_WIDTH) + u])
        texture_lists_column_major[tex_id] = column_major_pixels

    print("Inserting column major textures")
    for tex_id,tex_pixels in texture_lists_column_major.items():
        con.execute(
                """
                INSERT INTO textures_list_column_major
                VALUES(?,?,?,?)
                """,
                [tex_id,TEX_WIDTH,TEX_HEIGHT,tex_pixels]
                )

    sample_walls_sql_column_major = """
        SELECT SUM(l.pixels[(s.u * l.height) + s.v + 1]) AS checksum
        FROM textures_list_column_major AS l 
        JOIN samples AS s 
        ON s.texture_id = l.texture_id
    """

    print("Calculating column major sql checksum")
    checksum_duckdb_column_major = con.sql(sample_walls_sql_column_major).fetchall()[0][0]

    print(f"checksum duckdb column major {checksum_duckdb_column_major}")
    print(f"checksum python {checksum_python}")

    assert checksum_python == checksum_duckdb_column_major
    print("Column major checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(sample_walls_sql_column_major).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"Column major warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for wall like acesses COLUMN MAJOR")

    wall_like_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(sample_walls_sql_column_major).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    wall_like_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} wall like acesses COLUMN MAJOR: {wall_like_end - wall_like_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")

    print("""
        Result: List lookup for textures is very expensive in duckdb and does not compete with cedar_dbs byte reader
    """)

    print()
    print("Moving to one list per texture column")

    con.execute("""
        CREATE TABLE textures_col_based(
            texture_id INTEGER,
            col INTEGER,
            row UTINYINT[] NOT NULL,
            PRIMARY KEY(texture_id,col)
            )
    """)

    print("Creating texture column lists from original textures")
    for tex_id,tex_pixels in texture_lists.items():
        tex = {}
        for u in range(TEX_WIDTH):
            col = []
            for v in range(TEX_HEIGHT):
                col.append(tex_pixels[(v * TEX_WIDTH) + u])
            tex[u] = col

        for u,v in tex.items():
            con.execute("""
            INSERT INTO textures_col_based
            VALUES (?,?,?)
            """, [tex_id,u,v])

    con.sql("SELECT * FROM textures_col_based LIMIT 5").show()

    query = """
        SELECT SUM(t.row[s.v + 1]) AS res
        FROM textures_col_based AS t 
        JOIN samples AS s 
        ON t.texture_id = s.texture_id
        AND t.col = s.u 
    """

    print("Calculating texture column based sql checksum")
    checksum_duckdb_col_based = con.sql(query).fetchall()[0][0]

    print(f"checksum duckdb texture column based {checksum_duckdb_col_based}")
    print(f"checksum python {checksum_python}")

    assert checksum_python == checksum_duckdb_col_based
    print("Texture column based checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(query).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"Texture column based warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for wall like acesses TEXTURE COLUMN BASED")

    wall_like_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(query).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    wall_like_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} wall like acesses TEXTURE COLUMN BASED: {wall_like_end - wall_like_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")
























    print()
    print("Moving to one row per texture pixel")

    con.execute("""
        CREATE TABLE textures_pixel_based(
            texture_id INTEGER,
            u INTEGER,
            v INTEGER,
            palette_index UTINYINT NOT NULL,
            PRIMARY KEY(texture_id,u,v)
            )
    """)

    print("Creating texture pixel rows from original textures")
    for tex_id,tex_pixels in texture_lists.items():
        print(f"Creating tex {tex_id}/{NUM_TEXTURES} with {len(tex_pixels)} pixels")
        for v in range(TEX_HEIGHT):
            for u in range(TEX_WIDTH):
                palette_index = tex_pixels[(v * TEX_WIDTH) + u]
                con.execute("""
                INSERT INTO textures_pixel_based
                VALUES (?,?,?,?)
                """, [tex_id,u,v,palette_index])

    con.sql("SELECT * FROM textures_pixel_based LIMIT 5").show()

    pixel_query = """
        SELECT SUM(t.palette_index) AS res
        FROM textures_pixel_based AS t
        JOIN samples AS s
        ON t.texture_id = s.texture_id
        AND t.u = s.u
        AND t.v = s.v
    """

    print("Calculating texture pixel based sql checksum")
    checksum_duckdb_pixel_based = con.sql(pixel_query).fetchall()[0][0]

    print(f"checksum duckdb texture pixel based {checksum_duckdb_pixel_based}")
    print(f"checksum python {checksum_python}")

    assert checksum_python == checksum_duckdb_pixel_based
    print("Texture pixel based checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(pixel_query).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"Texture pixel based warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for wall like acesses TEXTURE PIXEL BASED")

    wall_like_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(pixel_query).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    wall_like_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} wall like acesses TEXTURE PIXEL BASED: {wall_like_end - wall_like_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")

    print()
    print("Moving to texture stored as BLOB")

    con.execute("""
        CREATE TABLE textures_blob(
            texture_id INTEGER PRIMARY KEY,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL,
            pixels BLOB NOT NULL
            )
    """)

    print("Creating BLOB textures from original textures")
    for tex_id,tex_pixels in texture_lists.items():
        con.execute("""
            INSERT INTO textures_blob
            VALUES (?,?,?,?)
        """, [tex_id,TEX_WIDTH,TEX_HEIGHT,bytes(tex_pixels)])

    blob_query = """
        SELECT SUM(
            b.pixels[
                (s.v * b.width) + s.u + 1:
                (s.v * b.width) + s.u + 1
            ]::BIT::INTEGER
        ) AS checksum
        FROM textures_blob AS b
        JOIN samples AS s
        ON b.texture_id = s.texture_id
    """

    print("Calculating BLOB based sql checksum")
    checksum_duckdb_blob = con.sql(blob_query).fetchall()[0][0]

    print(f"checksum duckdb BLOB based {checksum_duckdb_blob}")
    print(f"checksum python {checksum_python}")

    assert checksum_python == checksum_duckdb_blob
    print("BLOB based checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(blob_query).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"BLOB based warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for wall like acesses BLOB BASED")

    wall_like_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(blob_query).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    wall_like_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} wall like acesses BLOB BASED: {wall_like_end - wall_like_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")


    print()
    print("####################################################################################################")
    print("Testing texture table size with identical wall like sample accesses")

    texture_counts = [3,10,50,200]

    for texture_count in texture_counts:
        print()
        print(f"Creating texture column based table with {texture_count} textures")

        con.execute("""
            DROP TABLE IF EXISTS textures_col_based_count_test
        """)

        con.execute("""
            CREATE TABLE textures_col_based_count_test(
                texture_id INTEGER,
                col INTEGER,
                row UTINYINT[] NOT NULL,
                PRIMARY KEY(texture_id,col)
                )
        """)

        for tex_id in range(texture_count):
            print(f"Creating tex {tex_id}/{texture_count}")
            tex_pixels = __create_texture_lists_helper(tex_id)

            for u in range(TEX_WIDTH):
                col = []
                for v in range(TEX_HEIGHT):
                    col.append(tex_pixels[(v * TEX_WIDTH) + u])

                con.execute("""
                    INSERT INTO textures_col_based_count_test
                    VALUES (?,?,?)
                """, [tex_id,u,col])

        texture_count_query = """
            SELECT SUM(t.row[s.v + 1]) AS res
            FROM textures_col_based_count_test AS t
            JOIN samples AS s
            ON t.texture_id = s.texture_id
            AND t.col = s.u
        """

        warmup_start = time.perf_counter()
        for _ in range(NUM_WARMUP_RUNS):
            con.sql(texture_count_query).fetchall()[0][0]
        warmup_end = time.perf_counter()

        print(f"Warmup time for {texture_count} textures: {warmup_end - warmup_start} seconds")

        times = []
        for _ in range(NUM_RUNS):
            t_start = time.perf_counter()
            con.sql(texture_count_query).fetchall()[0][0]
            t_end = time.perf_counter()
            times.append((t_end - t_start) * 1000)

        mean = stats.mean(times)
        median = stats.median(times)
        std_dev = stats.stdev(times)

        print(f"Texture count: {texture_count}")
        print(f"Mean: {mean} ms")
        print(f"Median: {median} ms")
        print(f"Standard deviation: {std_dev:.2f} ms")

        if texture_count == texture_counts[0] or texture_count == texture_counts[-1]:
            print()
            print(f"EXPLAIN ANALYZE for {texture_count} textures")
            plan = con.sql("EXPLAIN ANALYZE " + texture_count_query).fetchall()[0][1]
            print(plan)


##################################################################################################################



    def create_flats_texture() -> list[int]:
        tex = []
        for _ in range(FLATS_WIDTH * FLATS_HEIGHT):
            tex.append(random.randint(0,255))
        assert len(tex) == FLATS_WIDTH * FLATS_HEIGHT
        return tex

    def sample_coordinates_flats(i: int):
        tex_id = (i // (FLATS_HEIGHT * FLATS_WIDTH)) % NUM_TEXTURES
        u = i % FLATS_HEIGHT
        v = (i // FLATS_HEIGHT) % FLATS_WIDTH

        return tex_id, u, v

    def sample_coordinates_flats_perspective(i: int):
        tex_id = (i // (FLATS_HEIGHT * FLATS_WIDTH)) % NUM_TEXTURES

        x = i % FLATS_WIDTH
        y = (i // FLATS_WIDTH) % FLATS_HEIGHT

        u = (x + 2 * y) % FLATS_WIDTH
        v = (2 * x + y) % FLATS_HEIGHT

        return tex_id, u, v

    def flats_lists_to_rows(flat: list[int]) -> dict[int,list[int]]:
        rows_dict = {}
        for i in range(FLATS_HEIGHT):
            rows_dict[i] = []
        
        index = 0
        for val in flat:
            row = index // FLATS_WIDTH
            rows_dict[row].append(val)
            index = index + 1

        return rows_dict












    print()
    print("####################################################################################################")
    print("Next access pattern FLATS")
    print("Creating FLATS")

    flats_textures = {}
    for i in range(NUM_TEXTURES):
        flats_textures[i] = create_flats_texture()
    assert len(flats_textures) == NUM_TEXTURES
    
    
    con.execute("""
        CREATE OR REPLACE TABLE flats_list (
            texture_id INTEGER PRIMARY KEY,
            width INTEGER,
            height INTEGER,
            pixels UTINYINT[]
        )
    """)
    
    for tex_id, pixels in flats_textures.items():

        con.execute("""
            INSERT INTO flats_list
            VALUES (?,?,?,?)

        """, [tex_id, FLATS_WIDTH, FLATS_HEIGHT, pixels])


    print("Creating sweep like samples")
    con.execute(""" CREATE OR REPLACE TABLE samples_flats_sweep (
                sample_id INTEGER PRIMARY KEY,
                texture_id INTEGER,
                u          INTEGER,
                v          INTEGER,
                )
            """)

    create_samples_flat_sweep = f""" 
    INSERT INTO samples_flats_sweep
    SELECT v.i AS sample_id,

    CAST(floor(v.i/ {FLATS_WIDTH* FLATS_HEIGHT})
    % {NUM_TEXTURES} AS INTEGER) AS texture_id,


    CAST(i % {FLATS_HEIGHT} AS INTEGER) AS u,
    CAST(floor(i/{FLATS_HEIGHT}) % {FLATS_WIDTH} AS INTEGER) AS v,

    FROM generate_series(0,{NUM_SAMPLES - 1}) v(i)

    """
    con.execute(create_samples_flat_sweep)
    
    print("Calculating checksums")
    checksum_python = 0
    for i in range(NUM_SAMPLES):
        tex_id, u, v = sample_coordinates_flats(i)
        checksum_python+= flats_textures[tex_id][(v*FLATS_WIDTH) + u]


    query_flats_list = f"""
        SELECT SUM(l.pixels[(s.v * {FLATS_WIDTH}) + s.u + 1]) AS res 
        FROM flats_list AS l 
        JOIN samples_flats_sweep AS s 
        ON l.texture_id = s.texture_id
    """
    checksum_duckdb = con.sql(query_flats_list).fetchall()[0][0]

    assert checksum_python == checksum_duckdb
    print("Checksum phase passed\n")


    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(query_flats_list).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"FLATS list warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for FLATS SWEEP LIST")

    flat_sweep_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(query_flats_list).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    flat_sweep_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} FLATS SWEEP LIST acesses: {flat_sweep_end - flat_sweep_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")


    con.execute("""
        CREATE OR REPLACE TABLE flats_rows (
            texture_id INTEGER,
            row INTEGER,
            pixels UTINYINT[],
            PRIMARY KEY (texture_id,row)
        )
    """)


    print("Creating flats row based representation")
    for texture_id, pixels in flats_textures.items():
        rows = flats_lists_to_rows(pixels)
        for row, elems in rows.items():
            con.execute("""
                INSERT INTO flats_rows 
                VALUES(?,?,?)
            """,[texture_id,row,elems])


    con.sql("SELECT * FROM flats_rows LIMIT 5").show()

    query_flats_rows = """
        SELECT SUM(r.pixels[s.u + 1])
        FROM flats_rows AS r 
        JOIN samples_flats_sweep AS s 
        ON s.texture_id = r.texture_id 
        AND s.v = r.row 
    """

    print("Calculating FLATS row based checksum")
    checksum_duckdb_rows = con.sql(query_flats_rows).fetchall()[0][0]

    print(f"checksum duckdb FLATS row based {checksum_duckdb_rows}")
    print(f"checksum python {checksum_python}")

    assert checksum_python == checksum_duckdb_rows
    print("FLATS row based checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(query_flats_rows).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"FLATS row based warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for FLATS SWEEP ROW BASED")

    flat_sweep_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(query_flats_rows).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    flat_sweep_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} FLATS SWEEP ROW BASED acesses: {flat_sweep_end - flat_sweep_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")


    print()
    print("Moving to one row per FLATS pixel")

    con.execute("""
        CREATE OR REPLACE TABLE flats_pixel_based(
            texture_id INTEGER,
            u INTEGER,
            v INTEGER,
            palette_index UTINYINT NOT NULL,
            PRIMARY KEY(texture_id,u,v)
        )
    """)

    print("Creating FLATS pixel rows from original FLATS")
    for texture_id,pixels in flats_textures.items():
        print(f"Creating tex {texture_id}/{NUM_TEXTURES} with {len(pixels)} pixels")
        for v in range(FLATS_HEIGHT):
            for u in range(FLATS_WIDTH):
                palette_index = pixels[(v * FLATS_WIDTH) + u]
                con.execute("""
                    INSERT INTO flats_pixel_based
                    VALUES (?,?,?,?)
                """, [texture_id,u,v,palette_index])

    con.sql("SELECT * FROM flats_pixel_based LIMIT 5").show()

    query_flats_pixel_based = """
        SELECT SUM(p.palette_index) AS res
        FROM flats_pixel_based AS p
        JOIN samples_flats_sweep AS s
        ON p.texture_id = s.texture_id
        AND p.u = s.u
        AND p.v = s.v
    """

    print("Calculating FLATS pixel based checksum")
    checksum_duckdb_pixel_based = con.sql(query_flats_pixel_based).fetchall()[0][0]

    print(f"checksum duckdb FLATS pixel based {checksum_duckdb_pixel_based}")
    print(f"checksum python {checksum_python}")

    assert checksum_python == checksum_duckdb_pixel_based
    print("FLATS pixel based checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(query_flats_pixel_based).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"FLATS pixel based warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for FLATS SWEEP PIXEL BASED")

    flat_sweep_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(query_flats_pixel_based).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    flat_sweep_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} FLATS SWEEP PIXEL BASED acesses: {flat_sweep_end - flat_sweep_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")

    print()
    print("Moving to FLATS stored as BLOB")

    con.execute("""
        CREATE OR REPLACE TABLE flats_blob(
            texture_id INTEGER PRIMARY KEY,
            width INTEGER,
            height INTEGER,
            pixels BLOB
        )
    """)

    print("Creating FLATS BLOB representation")
    for texture_id,pixels in flats_textures.items():
        con.execute("""
            INSERT INTO flats_blob
            VALUES (?,?,?,?)
        """, [texture_id,FLATS_WIDTH,FLATS_HEIGHT,bytes(pixels)])

    query_flats_blob = """
        SELECT SUM(
            b.pixels[
                (s.v * b.width) + s.u + 1:
                (s.v * b.width) + s.u + 1
            ]::BIT::INTEGER
        ) AS res
        FROM flats_blob AS b
        JOIN samples_flats_sweep AS s
        ON b.texture_id = s.texture_id
    """

    print("Calculating FLATS BLOB based checksum")
    checksum_duckdb_blob = con.sql(query_flats_blob).fetchall()[0][0]

    print(f"checksum duckdb FLATS BLOB based {checksum_duckdb_blob}")
    print(f"checksum python {checksum_python}")

    assert checksum_python == checksum_duckdb_blob
    print("FLATS BLOB based checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(query_flats_blob).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"FLATS BLOB based warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for FLATS SWEEP BLOB BASED")

    flat_sweep_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(query_flats_blob).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    flat_sweep_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} FLATS SWEEP BLOB BASED acesses: {flat_sweep_end - flat_sweep_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print()
    print("####################################################################################################")
    print("Next access pattern FLATS PERSPECTIVE LIKE")
    print("Creating perspective like samples")

    con.execute(""" CREATE OR REPLACE TABLE samples_flats_perspective (
                sample_id INTEGER PRIMARY KEY,
                texture_id INTEGER,
                u          INTEGER,
                v          INTEGER,
            )
        """)

    create_samples_flat_perspective = f"""
    INSERT INTO samples_flats_perspective
    SELECT p.i AS sample_id,

    CAST(floor(p.i / {FLATS_WIDTH * FLATS_HEIGHT})
    % {NUM_TEXTURES} AS INTEGER) AS texture_id,

    CAST((
        (p.i % {FLATS_WIDTH})
        + 2 * (floor(p.i / {FLATS_WIDTH}) % {FLATS_HEIGHT})
    ) % {FLATS_WIDTH} AS INTEGER) AS u,

    CAST((
        2 * (p.i % {FLATS_WIDTH})
        + (floor(p.i / {FLATS_WIDTH}) % {FLATS_HEIGHT})
    ) % {FLATS_HEIGHT} AS INTEGER) AS v

    FROM generate_series(0,{NUM_SAMPLES - 1}) p(i)
    """
    con.execute(create_samples_flat_perspective)

    con.sql("SELECT * FROM samples_flats_perspective LIMIT 10").show()

    print("Calculating FLATS PERSPECTIVE LIKE checksum")
    checksum_python_perspective = 0
    for i in range(NUM_SAMPLES):
        tex_id, u, v = sample_coordinates_flats_perspective(i)
        checksum_python_perspective += flats_textures[tex_id][(v * FLATS_WIDTH) + u]


    query_flats_list_perspective = f"""
        SELECT SUM(l.pixels[(s.v * {FLATS_WIDTH}) + s.u + 1]) AS res
        FROM flats_list AS l
        JOIN samples_flats_perspective AS s
        ON l.texture_id = s.texture_id
    """

    checksum_duckdb_perspective = con.sql(query_flats_list_perspective).fetchall()[0][0]

    print(f"checksum duckdb FLATS PERSPECTIVE LIKE list {checksum_duckdb_perspective}")
    print(f"checksum python {checksum_python_perspective}")

    assert checksum_python_perspective == checksum_duckdb_perspective
    print("FLATS PERSPECTIVE LIKE list checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(query_flats_list_perspective).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"FLATS PERSPECTIVE LIKE list warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for FLATS PERSPECTIVE LIKE LIST")

    flat_perspective_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(query_flats_list_perspective).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    flat_perspective_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} FLATS PERSPECTIVE LIKE LIST acesses: {flat_perspective_end - flat_perspective_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")


    query_flats_rows_perspective = """
        SELECT SUM(r.pixels[s.u + 1])
        FROM flats_rows AS r
        JOIN samples_flats_perspective AS s
        ON s.texture_id = r.texture_id
        AND s.v = r.row
    """

    print()
    print("Calculating FLATS PERSPECTIVE LIKE row based checksum")
    checksum_duckdb_rows_perspective = con.sql(query_flats_rows_perspective).fetchall()[0][0]

    print(f"checksum duckdb FLATS PERSPECTIVE LIKE row based {checksum_duckdb_rows_perspective}")
    print(f"checksum python {checksum_python_perspective}")

    assert checksum_python_perspective == checksum_duckdb_rows_perspective
    print("FLATS PERSPECTIVE LIKE row based checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(query_flats_rows_perspective).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"FLATS PERSPECTIVE LIKE row based warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for FLATS PERSPECTIVE LIKE ROW BASED")

    flat_perspective_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(query_flats_rows_perspective).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    flat_perspective_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} FLATS PERSPECTIVE LIKE ROW BASED acesses: {flat_perspective_end - flat_perspective_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")


    query_flats_pixel_based_perspective = """
        SELECT SUM(p.palette_index) AS res
        FROM flats_pixel_based AS p
        JOIN samples_flats_perspective AS s
        ON p.texture_id = s.texture_id
        AND p.u = s.u
        AND p.v = s.v
    """

    print()
    print("Calculating FLATS PERSPECTIVE LIKE pixel based checksum")
    checksum_duckdb_pixel_based_perspective = con.sql(query_flats_pixel_based_perspective).fetchall()[0][0]

    print(f"checksum duckdb FLATS PERSPECTIVE LIKE pixel based {checksum_duckdb_pixel_based_perspective}")
    print(f"checksum python {checksum_python_perspective}")

    assert checksum_python_perspective == checksum_duckdb_pixel_based_perspective
    print("FLATS PERSPECTIVE LIKE pixel based checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(query_flats_pixel_based_perspective).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"FLATS PERSPECTIVE LIKE pixel based warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for FLATS PERSPECTIVE LIKE PIXEL BASED")

    flat_perspective_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(query_flats_pixel_based_perspective).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    flat_perspective_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} FLATS PERSPECTIVE LIKE PIXEL BASED acesses: {flat_perspective_end - flat_perspective_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")


    query_flats_blob_perspective = """
        SELECT SUM(
            b.pixels[
                (s.v * b.width) + s.u + 1:
                (s.v * b.width) + s.u + 1
            ]::BIT::INTEGER
        ) AS res
        FROM flats_blob AS b
        JOIN samples_flats_perspective AS s
        ON b.texture_id = s.texture_id
    """

    print()
    print("Calculating FLATS PERSPECTIVE LIKE BLOB based checksum")
    checksum_duckdb_blob_perspective = con.sql(query_flats_blob_perspective).fetchall()[0][0]

    print(f"checksum duckdb FLATS PERSPECTIVE LIKE BLOB based {checksum_duckdb_blob_perspective}")
    print(f"checksum python {checksum_python_perspective}")

    assert checksum_python_perspective == checksum_duckdb_blob_perspective
    print("FLATS PERSPECTIVE LIKE BLOB based checksum phase passed")

    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(query_flats_blob_perspective).fetchall()[0][0]
    warmup_end = time.perf_counter()
    print(f"FLATS PERSPECTIVE LIKE BLOB based warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print("Beginning benchmark for FLATS PERSPECTIVE LIKE BLOB BASED")

    flat_perspective_begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(query_flats_blob_perspective).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    flat_perspective_end = time.perf_counter()
    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} FLATS PERSPECTIVE LIKE BLOB BASED acesses: {flat_perspective_end - flat_perspective_begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")



    ##################################################################################################################


    def create_sprite_texture(id: int) -> list[int]:
        sprite = []
        random.seed(id + 10000)
        for _ in range(SPRITE_WIDTH * SPRITE_HEIGHT):
            sprite.append(random.randint(0,255))

        assert len(sprite) == SPRITE_WIDTH * SPRITE_HEIGHT
        return sprite

    def sprite_list_to_columns(sprite: list[int]) -> dict[int,list[int]]:
        cols_dict = {}
        for i in range(SPRITE_WIDTH):
            cols_dict[i] = []

        for u in range(SPRITE_WIDTH):
            for v in range(SPRITE_HEIGHT):
                cols_dict[u].append(sprite[(v * SPRITE_WIDTH) + u])

        return cols_dict

    def sample_coordinates_sprite(i: int, scale: float):
        sprite_id = i % NUM_TEXTURES
        local_i = i // NUM_TEXTURES

        projected_width = int(SPRITE_WIDTH * scale)
        projected_height = int(SPRITE_HEIGHT * scale)
        projected_area = projected_width * projected_height

        samples_for_sprite = (
            NUM_SAMPLES + NUM_TEXTURES - 1 - sprite_id
        ) // NUM_TEXTURES

        projected_i = (
            local_i * projected_area
        ) // samples_for_sprite

        screen_x = projected_i % projected_width
        screen_y = projected_i // projected_width

        u = min(SPRITE_WIDTH - 1, int(screen_x // scale))
        v = min(SPRITE_HEIGHT - 1, int(screen_y // scale))

        return sprite_id, u, v


    print()
    print("####################################################################################################")
    print("Next access pattern SPRITES")
    print("Creating SPRITES")

    sprite_textures = {}
    for i in range(NUM_TEXTURES):
        sprite_textures[i] = create_sprite_texture(i)
    assert len(sprite_textures) == NUM_TEXTURES


    print("Creating SPRITES list representation")
    con.execute("""
        CREATE OR REPLACE TABLE sprites_list (
            sprite_id INTEGER PRIMARY KEY,
            width INTEGER,
            height INTEGER,
            pixels UTINYINT[]
        )
    """)

    for sprite_id,pixels in sprite_textures.items():
        con.execute("""
            INSERT INTO sprites_list
            VALUES (?,?,?,?)
        """, [sprite_id,SPRITE_WIDTH,SPRITE_HEIGHT,pixels])


    print("Creating SPRITES column based representation")
    con.execute("""
        CREATE OR REPLACE TABLE sprites_col_based(
            sprite_id INTEGER,
            col INTEGER,
            row UTINYINT[] NOT NULL,
            PRIMARY KEY(sprite_id,col)
        )
    """)

    for sprite_id,pixels in sprite_textures.items():
        cols = sprite_list_to_columns(pixels)
        for col, elems in cols.items():
            con.execute("""
                INSERT INTO sprites_col_based
                VALUES (?,?,?)
            """, [sprite_id,col,elems])

    con.sql("SELECT * FROM sprites_col_based LIMIT 5").show()


    print("Creating SPRITES pixel based representation")
    con.execute("""
        CREATE OR REPLACE TABLE sprites_pixel_based(
            sprite_id INTEGER,
            u INTEGER,
            v INTEGER,
            palette_index UTINYINT NOT NULL,
            PRIMARY KEY(sprite_id,u,v)
        )
    """)

    for sprite_id,pixels in sprite_textures.items():
        print(f"Creating sprite {sprite_id}/{NUM_TEXTURES} with {len(pixels)} pixels")
        for v in range(SPRITE_HEIGHT):
            for u in range(SPRITE_WIDTH):
                palette_index = pixels[(v * SPRITE_WIDTH) + u]
                con.execute("""
                    INSERT INTO sprites_pixel_based
                    VALUES (?,?,?,?)
                """, [sprite_id,u,v,palette_index])

    con.sql("SELECT * FROM sprites_pixel_based LIMIT 5").show()


    print("Creating SPRITES BLOB representation")
    con.execute("""
        CREATE OR REPLACE TABLE sprites_blob(
            sprite_id INTEGER PRIMARY KEY,
            width INTEGER,
            height INTEGER,
            pixels BLOB
        )
    """)

    for sprite_id,pixels in sprite_textures.items():
        con.execute("""
            INSERT INTO sprites_blob
            VALUES (?,?,?,?)
        """, [sprite_id,SPRITE_WIDTH,SPRITE_HEIGHT,bytes(pixels)])


    sprite_scales = [
        ("HALF", 0.5),
        ("ONE", 1.0),
        ("TWO", 2.0),
    ]

    for scale_name, scale in sprite_scales:
        print()
        print(f"Creating SPRITE samples SCALE {scale_name} ({scale})")

        sample_table = f"samples_sprite_scale_{scale_name.lower()}"

        con.execute(f"""
            CREATE OR REPLACE TABLE {sample_table} (
                sample_id INTEGER PRIMARY KEY,
                sprite_id INTEGER,
                u INTEGER,
                v INTEGER
            )
        """)

        projected_width = int(SPRITE_WIDTH * scale)
        projected_height = int(SPRITE_HEIGHT * scale)

        con.execute(f"""
            INSERT INTO {sample_table}
            WITH base AS (
                SELECT
                    i,
                    CAST(i % {NUM_TEXTURES} AS INTEGER) AS sprite_id,
                    CAST(FLOOR(i / {NUM_TEXTURES}) AS BIGINT) AS local_i
                FROM generate_series(0,{NUM_SAMPLES - 1}) v(i)
            ),
            spread AS (
                SELECT
                    i,
                    sprite_id,
                    CAST(FLOOR(
                        (
                            local_i * {projected_width * projected_height}
                        )
                        /
                        FLOOR(
                            (
                                {NUM_SAMPLES} + {NUM_TEXTURES} - 1 - sprite_id
                            )
                            / {NUM_TEXTURES}
                        )
                    ) AS BIGINT) AS projected_i
                FROM base
            )
            SELECT
                i AS sample_id,
                sprite_id,

                CAST(LEAST(
                    {SPRITE_WIDTH - 1},
                    FLOOR(
                        (projected_i % {projected_width}) / {scale}
                    )
                ) AS INTEGER) AS u,

                CAST(LEAST(
                    {SPRITE_HEIGHT - 1},
                    FLOOR(
                        FLOOR(projected_i / {projected_width}) / {scale}
                    )
                ) AS INTEGER) AS v

            FROM spread
        """)

        con.sql(f"SELECT * FROM {sample_table} LIMIT 10").show()


        print(f"Calculating SPRITE SCALE {scale_name} python checksum")
        checksum_python_sprite = 0
        for i in range(NUM_SAMPLES):
            sprite_id, u, v = sample_coordinates_sprite(i,scale)
            checksum_python_sprite += sprite_textures[sprite_id][(v * SPRITE_WIDTH) + u]


        query_sprite_list = f"""
            SELECT SUM(l.pixels[(s.v * l.width) + s.u + 1]) AS res
            FROM sprites_list AS l
            JOIN {sample_table} AS s
            ON l.sprite_id = s.sprite_id
        """

        print(f"Calculating SPRITE SCALE {scale_name} list checksum")
        checksum_duckdb_sprite_list = con.sql(query_sprite_list).fetchall()[0][0]

        print(f"checksum duckdb SPRITE SCALE {scale_name} list {checksum_duckdb_sprite_list}")
        print(f"checksum python {checksum_python_sprite}")

        assert checksum_python_sprite == checksum_duckdb_sprite_list
        print(f"SPRITE SCALE {scale_name} list checksum phase passed")

        warmup_start = time.perf_counter()
        for _ in range(NUM_WARMUP_RUNS):
            con.sql(query_sprite_list).fetchall()[0][0]
        warmup_end = time.perf_counter()
        print(f"SPRITE SCALE {scale_name} list warmup time elapsed {warmup_end - warmup_start} seconds")

        print()
        print("####################################################################################################")
        print(f"Beginning benchmark for SPRITE SCALE {scale_name} LIST")

        sprite_begin = time.perf_counter()
        times = []
        for _ in range(NUM_RUNS):
            t_start = time.perf_counter()
            con.sql(query_sprite_list).fetchall()[0][0]
            t_end = time.perf_counter()
            times.append((t_end - t_start) * 1000)
        sprite_end = time.perf_counter()
        mean = stats.mean(times)
        median = stats.median(times)
        std_dev = stats.stdev(times)

        print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} SPRITE SCALE {scale_name} LIST acesses: {sprite_end - sprite_begin} seconds")
        print(f"Mean: {mean} ms")
        print(f"Median: {median} ms")
        print(f"Standard deviation: {std_dev:.2f} ms")


        query_sprite_col_based = f"""
            SELECT SUM(c.row[s.v + 1]) AS res
            FROM sprites_col_based AS c
            JOIN {sample_table} AS s
            ON c.sprite_id = s.sprite_id
            AND c.col = s.u
        """

        print()
        print(f"Calculating SPRITE SCALE {scale_name} column based checksum")
        checksum_duckdb_sprite_col = con.sql(query_sprite_col_based).fetchall()[0][0]

        print(f"checksum duckdb SPRITE SCALE {scale_name} column based {checksum_duckdb_sprite_col}")
        print(f"checksum python {checksum_python_sprite}")

        assert checksum_python_sprite == checksum_duckdb_sprite_col
        print(f"SPRITE SCALE {scale_name} column based checksum phase passed")

        warmup_start = time.perf_counter()
        for _ in range(NUM_WARMUP_RUNS):
            con.sql(query_sprite_col_based).fetchall()[0][0]
        warmup_end = time.perf_counter()
        print(f"SPRITE SCALE {scale_name} column based warmup time elapsed {warmup_end - warmup_start} seconds")

        print()
        print("####################################################################################################")
        print(f"Beginning benchmark for SPRITE SCALE {scale_name} COLUMN BASED")

        sprite_begin = time.perf_counter()
        times = []
        for _ in range(NUM_RUNS):
            t_start = time.perf_counter()
            con.sql(query_sprite_col_based).fetchall()[0][0]
            t_end = time.perf_counter()
            times.append((t_end - t_start) * 1000)
        sprite_end = time.perf_counter()
        mean = stats.mean(times)
        median = stats.median(times)
        std_dev = stats.stdev(times)

        print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} SPRITE SCALE {scale_name} COLUMN BASED acesses: {sprite_end - sprite_begin} seconds")
        print(f"Mean: {mean} ms")
        print(f"Median: {median} ms")
        print(f"Standard deviation: {std_dev:.2f} ms")


        query_sprite_pixel_based = f"""
            SELECT SUM(p.palette_index) AS res
            FROM sprites_pixel_based AS p
            JOIN {sample_table} AS s
            ON p.sprite_id = s.sprite_id
            AND p.u = s.u
            AND p.v = s.v
        """

        print()
        print(f"Calculating SPRITE SCALE {scale_name} pixel based checksum")
        checksum_duckdb_sprite_pixel = con.sql(query_sprite_pixel_based).fetchall()[0][0]

        print(f"checksum duckdb SPRITE SCALE {scale_name} pixel based {checksum_duckdb_sprite_pixel}")
        print(f"checksum python {checksum_python_sprite}")

        assert checksum_python_sprite == checksum_duckdb_sprite_pixel
        print(f"SPRITE SCALE {scale_name} pixel based checksum phase passed")

        warmup_start = time.perf_counter()
        for _ in range(NUM_WARMUP_RUNS):
            con.sql(query_sprite_pixel_based).fetchall()[0][0]
        warmup_end = time.perf_counter()
        print(f"SPRITE SCALE {scale_name} pixel based warmup time elapsed {warmup_end - warmup_start} seconds")

        print()
        print("####################################################################################################")
        print(f"Beginning benchmark for SPRITE SCALE {scale_name} PIXEL BASED")

        sprite_begin = time.perf_counter()
        times = []
        for _ in range(NUM_RUNS):
            t_start = time.perf_counter()
            con.sql(query_sprite_pixel_based).fetchall()[0][0]
            t_end = time.perf_counter()
            times.append((t_end - t_start) * 1000)
        sprite_end = time.perf_counter()
        mean = stats.mean(times)
        median = stats.median(times)
        std_dev = stats.stdev(times)

        print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} SPRITE SCALE {scale_name} PIXEL BASED acesses: {sprite_end - sprite_begin} seconds")
        print(f"Mean: {mean} ms")
        print(f"Median: {median} ms")
        print(f"Standard deviation: {std_dev:.2f} ms")


        query_sprite_blob = f"""
            SELECT SUM(
                b.pixels[
                    (s.v * b.width) + s.u + 1:
                    (s.v * b.width) + s.u + 1
                ]::BIT::INTEGER
            ) AS res
            FROM sprites_blob AS b
            JOIN {sample_table} AS s
            ON b.sprite_id = s.sprite_id
        """

        print()
        print(f"Calculating SPRITE SCALE {scale_name} BLOB based checksum")
        checksum_duckdb_sprite_blob = con.sql(query_sprite_blob).fetchall()[0][0]

        print(f"checksum duckdb SPRITE SCALE {scale_name} BLOB based {checksum_duckdb_sprite_blob}")
        print(f"checksum python {checksum_python_sprite}")

        assert checksum_python_sprite == checksum_duckdb_sprite_blob
        print(f"SPRITE SCALE {scale_name} BLOB based checksum phase passed")

        warmup_start = time.perf_counter()
        for _ in range(NUM_WARMUP_RUNS):
            con.sql(query_sprite_blob).fetchall()[0][0]
        warmup_end = time.perf_counter()
        print(f"SPRITE SCALE {scale_name} BLOB based warmup time elapsed {warmup_end - warmup_start} seconds")

        print()
        print("####################################################################################################")
        print(f"Beginning benchmark for SPRITE SCALE {scale_name} BLOB BASED")

        sprite_begin = time.perf_counter()
        times = []
        for _ in range(NUM_RUNS):
            t_start = time.perf_counter()
            con.sql(query_sprite_blob).fetchall()[0][0]
            t_end = time.perf_counter()
            times.append((t_end - t_start) * 1000)
        sprite_end = time.perf_counter()
        mean = stats.mean(times)
        median = stats.median(times)
        std_dev = stats.stdev(times)

        print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} SPRITE SCALE {scale_name} BLOB BASED acesses: {sprite_end - sprite_begin} seconds")
        print(f"Mean: {mean} ms")
        print(f"Median: {median} ms")
        print(f"Standard deviation: {std_dev:.2f} ms")



    ##################################################################################################################


    print()
    print("####################################################################################################")
    print("Next access pattern SPRITE TRANSPARENCY")
    print("Comparing dense pixels + mask against sparse visible pixel rows")

    def create_sprite_opacity_mask(sprite_id: int, opacity: float) -> list[int]:
        total_pixels = SPRITE_WIDTH * SPRITE_HEIGHT
        visible_pixels = round(total_pixels * opacity)

        center_x = (SPRITE_WIDTH - 1) / 2 + ((sprite_id % 5) - 2) * 0.5
        center_y = (SPRITE_HEIGHT - 1) / 2 + (((sprite_id // 5) % 5) - 2) * 0.5

        coordinates = []
        for v in range(SPRITE_HEIGHT):
            for u in range(SPRITE_WIDTH):
                distance = (
                    ((u - center_x) / (SPRITE_WIDTH / 2)) ** 2
                    + ((v - center_y) / (SPRITE_HEIGHT / 2)) ** 2
                )
                coordinates.append((distance,v,u))

        coordinates.sort()

        mask = [0] * total_pixels
        for _,v,u in coordinates[:visible_pixels]:
            mask[(v * SPRITE_WIDTH) + u] = 1

        assert sum(mask) == visible_pixels
        return mask


    opacity_levels = [
        ("100", 1.00),
        ("75", 0.75),
        ("50", 0.50),
        ("25", 0.25),
    ]


    for opacity_name, opacity in opacity_levels:
        print()
        print("####################################################################################################")
        print(f"Creating SPRITE TRANSPARENCY {opacity_name}% opacity")

        sprite_masks = {}
        for sprite_id in range(NUM_TEXTURES):
            sprite_masks[sprite_id] = create_sprite_opacity_mask(sprite_id,opacity)

        total_visible_storage_pixels = sum(sum(mask) for mask in sprite_masks.values())
        total_possible_storage_pixels = NUM_TEXTURES * SPRITE_WIDTH * SPRITE_HEIGHT

        print(f"SPRITE TRANSPARENCY {opacity_name}% total possible pixels: {total_possible_storage_pixels}")
        print(f"SPRITE TRANSPARENCY {opacity_name}% visible pixels stored sparsely: {total_visible_storage_pixels}")


        print(f"Creating SPRITE TRANSPARENCY {opacity_name}% dense BLOB + mask representation")
        con.execute("""
            CREATE OR REPLACE TABLE sprites_blob_masked(
                sprite_id INTEGER PRIMARY KEY,
                width INTEGER,
                height INTEGER,
                pixels BLOB,
                mask BLOB
            )
        """)

        for sprite_id,pixels in sprite_textures.items():
            con.execute("""
                INSERT INTO sprites_blob_masked
                VALUES (?,?,?,?,?)
            """, [
                sprite_id,
                SPRITE_WIDTH,
                SPRITE_HEIGHT,
                bytes(pixels),
                bytes(sprite_masks[sprite_id]),
            ])


        print(f"Creating SPRITE TRANSPARENCY {opacity_name}% sparse pixel representation")
        con.execute("""
            CREATE OR REPLACE TABLE sprites_pixel_based_sparse(
                sprite_id INTEGER,
                u INTEGER,
                v INTEGER,
                palette_index UTINYINT NOT NULL,
                PRIMARY KEY(sprite_id,u,v)
            )
        """)

        for sprite_id,pixels in sprite_textures.items():
            sparse_rows = []
            mask = sprite_masks[sprite_id]

            for v in range(SPRITE_HEIGHT):
                for u in range(SPRITE_WIDTH):
                    offset = (v * SPRITE_WIDTH) + u
                    if mask[offset] != 0:
                        sparse_rows.append((
                            sprite_id,
                            u,
                            v,
                            pixels[offset],
                        ))

            print(f"Creating sparse sprite {sprite_id}/{NUM_TEXTURES} with {len(sparse_rows)} visible pixels")

            if sparse_rows:
                con.executemany("""
                    INSERT INTO sprites_pixel_based_sparse
                    VALUES (?,?,?,?)
                """, sparse_rows)

        sparse_row_count = con.sql("""
            SELECT COUNT(*)
            FROM sprites_pixel_based_sparse
        """).fetchall()[0][0]

        print(f"SPRITE TRANSPARENCY {opacity_name}% sparse table row count: {sparse_row_count}")
        assert sparse_row_count == total_visible_storage_pixels


        for scale_name, scale in sprite_scales:
            sample_table = f"samples_sprite_scale_{scale_name.lower()}"

            print()
            print("####################################################################################################")
            print(f"Calculating SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} python checksum and visible count")

            checksum_python_sprite_transparency = 0
            visible_count_python_sprite_transparency = 0

            for i in range(NUM_SAMPLES):
                sprite_id, u, v = sample_coordinates_sprite(i,scale)
                offset = (v * SPRITE_WIDTH) + u

                if sprite_masks[sprite_id][offset] != 0:
                    checksum_python_sprite_transparency += sprite_textures[sprite_id][offset]
                    visible_count_python_sprite_transparency += 1


            query_sprite_dense_mask = f"""
                SELECT
                    SUM(
                        b.pixels[
                            (s.v * b.width) + s.u + 1:
                            (s.v * b.width) + s.u + 1
                        ]::BIT::INTEGER
                    ) AS checksum,
                    COUNT(*) AS visible_count
                FROM sprites_blob_masked AS b
                JOIN {sample_table} AS s
                ON b.sprite_id = s.sprite_id
                WHERE b.mask[
                    (s.v * b.width) + s.u + 1:
                    (s.v * b.width) + s.u + 1
                ]::BIT::INTEGER <> 0
            """

            print(f"Calculating SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} dense BLOB + mask checksum")
            dense_result = con.sql(query_sprite_dense_mask).fetchall()[0]
            checksum_duckdb_sprite_dense_mask = dense_result[0] if dense_result[0] is not None else 0
            visible_count_duckdb_sprite_dense_mask = dense_result[1]

            print(f"checksum duckdb SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} dense BLOB + mask {checksum_duckdb_sprite_dense_mask}")
            print(f"checksum python {checksum_python_sprite_transparency}")
            print(f"visible count duckdb SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} dense BLOB + mask {visible_count_duckdb_sprite_dense_mask}")
            print(f"visible count python {visible_count_python_sprite_transparency}")

            assert checksum_python_sprite_transparency == checksum_duckdb_sprite_dense_mask
            assert visible_count_python_sprite_transparency == visible_count_duckdb_sprite_dense_mask
            print(f"SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} dense BLOB + mask checksum and visible count phase passed")

            warmup_start = time.perf_counter()
            for _ in range(NUM_WARMUP_RUNS):
                con.sql(query_sprite_dense_mask).fetchall()[0]
            warmup_end = time.perf_counter()
            print(f"SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} dense BLOB + mask warmup time elapsed {warmup_end - warmup_start} seconds")

            print()
            print("####################################################################################################")
            print(f"Beginning benchmark for SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} DENSE BLOB + MASK")

            sprite_begin = time.perf_counter()
            times = []
            for _ in range(NUM_RUNS):
                t_start = time.perf_counter()
                con.sql(query_sprite_dense_mask).fetchall()[0]
                t_end = time.perf_counter()
                times.append((t_end - t_start) * 1000)
            sprite_end = time.perf_counter()
            mean = stats.mean(times)
            median = stats.median(times)
            std_dev = stats.stdev(times)

            print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} DENSE BLOB + MASK acesses: {sprite_end - sprite_begin} seconds")
            print(f"Mean: {mean} ms")
            print(f"Median: {median} ms")
            print(f"Standard deviation: {std_dev:.2f} ms")


            query_sprite_sparse = f"""
                SELECT
                    SUM(p.palette_index) AS checksum,
                    COUNT(*) AS visible_count
                FROM sprites_pixel_based_sparse AS p
                JOIN {sample_table} AS s
                ON p.sprite_id = s.sprite_id
                AND p.u = s.u
                AND p.v = s.v
            """

            print()
            print(f"Calculating SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} sparse pixel checksum")
            sparse_result = con.sql(query_sprite_sparse).fetchall()[0]
            checksum_duckdb_sprite_sparse = sparse_result[0] if sparse_result[0] is not None else 0
            visible_count_duckdb_sprite_sparse = sparse_result[1]

            print(f"checksum duckdb SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} sparse pixel {checksum_duckdb_sprite_sparse}")
            print(f"checksum python {checksum_python_sprite_transparency}")
            print(f"visible count duckdb SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} sparse pixel {visible_count_duckdb_sprite_sparse}")
            print(f"visible count python {visible_count_python_sprite_transparency}")

            assert checksum_python_sprite_transparency == checksum_duckdb_sprite_sparse
            assert visible_count_python_sprite_transparency == visible_count_duckdb_sprite_sparse
            print(f"SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} sparse pixel checksum and visible count phase passed")

            warmup_start = time.perf_counter()
            for _ in range(NUM_WARMUP_RUNS):
                con.sql(query_sprite_sparse).fetchall()[0]
            warmup_end = time.perf_counter()
            print(f"SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} sparse pixel warmup time elapsed {warmup_end - warmup_start} seconds")

            print()
            print("####################################################################################################")
            print(f"Beginning benchmark for SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} SPARSE PIXEL")

            sprite_begin = time.perf_counter()
            times = []
            for _ in range(NUM_RUNS):
                t_start = time.perf_counter()
                con.sql(query_sprite_sparse).fetchall()[0]
                t_end = time.perf_counter()
                times.append((t_end - t_start) * 1000)
            sprite_end = time.perf_counter()
            mean = stats.mean(times)
            median = stats.median(times)
            std_dev = stats.stdev(times)

            print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} SPRITE TRANSPARENCY {opacity_name}% SCALE {scale_name} SPARSE PIXEL acesses: {sprite_end - sprite_begin} seconds")
            print(f"Mean: {mean} ms")
            print(f"Median: {median} ms")
            print(f"Standard deviation: {std_dev:.2f} ms")


if __name__ == "__main__":
    main()




