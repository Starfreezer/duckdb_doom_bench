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

NUM_WARMUP_RUNS = 5
NUM_RUNS = 50


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


if __name__ == "__main__":
    main()




