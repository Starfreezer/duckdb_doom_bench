import time
import random
import statistics as stats

import duckdb


TEXTURE_COUNTS = [50,200,500,1000]

NUM_SAMPLES = 20000

TEX_WIDTH = 64
TEX_HEIGHT = 128

FLATS_WIDTH = 64
FLATS_HEIGHT = 64

FIXED_WORKING_SET_TEXTURES = 3

NUM_WARMUP_RUNS = 50
NUM_RUNS = 500


def __create_texture_lists_helper (id: int) -> list[int]:
    texture = []
    random.seed(id)
    for _ in range(TEX_WIDTH * TEX_HEIGHT):
        texture.append(random.randint(0,255))

    assert len(texture) == TEX_WIDTH * TEX_HEIGHT
    return texture


def __create_flats_texture_helper(id: int) -> list[int]:
    texture = []
    random.seed(id + 1000000)
    for _ in range(FLATS_WIDTH * FLATS_HEIGHT):
        texture.append(random.randint(0,255))

    assert len(texture) == FLATS_WIDTH * FLATS_HEIGHT
    return texture


def benchmark_query(con, query: str, description: str):
    warmup_start = time.perf_counter()
    for _ in range(NUM_WARMUP_RUNS):
        con.sql(query).fetchall()[0][0]
    warmup_end = time.perf_counter()

    print(f"{description} warmup time elapsed {warmup_end - warmup_start} seconds")

    print()
    print("####################################################################################################")
    print(f"Beginning benchmark for {description}")

    begin = time.perf_counter()
    times = []
    for _ in range(NUM_RUNS):
        t_start = time.perf_counter()
        con.sql(query).fetchall()[0][0]
        t_end = time.perf_counter()
        times.append((t_end - t_start) * 1000)
    end = time.perf_counter()

    mean = stats.mean(times)
    median = stats.median(times)
    std_dev = stats.stdev(times)

    print(f"Total time taken for {NUM_RUNS * NUM_SAMPLES} {description} acesses: {end - begin} seconds")
    print(f"Mean: {mean} ms")
    print(f"Median: {median} ms")
    print(f"Standard deviation: {std_dev:.2f} ms")


def create_wall_samples_fixed(con):
    print("Creating WALL fixed working set samples")

    con.execute(f"""
        CREATE TABLE samples_wall_fixed AS
        SELECT
            i AS sample_id,

            CAST(
                FLOOR(i / {TEX_WIDTH * TEX_HEIGHT})
                % {FIXED_WORKING_SET_TEXTURES}
                AS INTEGER
            ) AS texture_id,

            CAST(FLOOR(i / {TEX_HEIGHT}) % {TEX_WIDTH} AS INTEGER) AS u,
            CAST(i % {TEX_HEIGHT} AS INTEGER) AS v

        FROM generate_series(0,{NUM_SAMPLES - 1}) v(i)
    """)


def create_wall_samples_spread(con, texture_count: int):
    print(f"Creating WALL spread working set samples for {texture_count} textures")

    con.execute(f"""
        CREATE TABLE samples_wall_spread AS
        WITH base AS (
            SELECT
                i,
                CAST(i % {texture_count} AS INTEGER) AS texture_id,
                CAST(FLOOR(i / {texture_count}) AS BIGINT) AS local_i
            FROM generate_series(0,{NUM_SAMPLES - 1}) v(i)
        ),
        spread AS (
            SELECT
                i,
                texture_id,
                CAST(FLOOR(
                    (
                        local_i * {TEX_WIDTH * TEX_HEIGHT}
                    )
                    /
                    FLOOR(
                        (
                            {NUM_SAMPLES} + {texture_count} - 1 - texture_id
                        )
                        / {texture_count}
                    )
                ) AS BIGINT) AS projected_i
            FROM base
        )
        SELECT
            i AS sample_id,
            texture_id,
            CAST(FLOOR(projected_i / {TEX_HEIGHT}) AS INTEGER) AS u,
            CAST(projected_i % {TEX_HEIGHT} AS INTEGER) AS v
        FROM spread
    """)


def create_flat_samples_fixed(con):
    print("Creating FLATS fixed working set samples")

    con.execute(f"""
        CREATE TABLE samples_flats_fixed AS
        SELECT
            i AS sample_id,

            CAST(
                FLOOR(i / {FLATS_WIDTH * FLATS_HEIGHT})
                % {FIXED_WORKING_SET_TEXTURES}
                AS INTEGER
            ) AS texture_id,

            CAST(i % {FLATS_WIDTH} AS INTEGER) AS u,
            CAST(FLOOR(i / {FLATS_WIDTH}) % {FLATS_HEIGHT} AS INTEGER) AS v

        FROM generate_series(0,{NUM_SAMPLES - 1}) v(i)
    """)


def create_flat_samples_spread(con, texture_count: int):
    print(f"Creating FLATS spread working set samples for {texture_count} textures")

    con.execute(f"""
        CREATE TABLE samples_flats_spread AS
        WITH base AS (
            SELECT
                i,
                CAST(i % {texture_count} AS INTEGER) AS texture_id,
                CAST(FLOOR(i / {texture_count}) AS BIGINT) AS local_i
            FROM generate_series(0,{NUM_SAMPLES - 1}) v(i)
        ),
        spread AS (
            SELECT
                i,
                texture_id,
                CAST(FLOOR(
                    (
                        local_i * {FLATS_WIDTH * FLATS_HEIGHT}
                    )
                    /
                    FLOOR(
                        (
                            {NUM_SAMPLES} + {texture_count} - 1 - texture_id
                        )
                        / {texture_count}
                    )
                ) AS BIGINT) AS projected_i
            FROM base
        )
        SELECT
            i AS sample_id,
            texture_id,
            CAST(projected_i % {FLATS_WIDTH} AS INTEGER) AS u,
            CAST(FLOOR(projected_i / {FLATS_WIDTH}) AS INTEGER) AS v
        FROM spread
    """)


def benchmark_walls(texture_count: int):
    print()
    print()
    print("####################################################################################################")
    print("####################################################################################################")
    print(f"WALL SCALING BENCHMARK WITH {texture_count} TEXTURES")
    print("####################################################################################################")
    print("####################################################################################################")

    con = duckdb.connect(
        ":memory:",
        config={"threads": 1},
    )

    create_wall_samples_fixed(con)
    create_wall_samples_spread(con,texture_count)

    print()
    print(f"Creating WALL column based representation with {texture_count} textures")

    con.execute("""
        CREATE TABLE textures_col_based(
            texture_id INTEGER,
            col INTEGER,
            row UTINYINT[] NOT NULL,
            PRIMARY KEY(texture_id,col)
        )
    """)

    grouped_build_start = time.perf_counter()

    for tex_id in range(texture_count):
        if tex_id % 50 == 0:
            print(f"Creating WALL texture {tex_id}/{texture_count}")

        tex_pixels = __create_texture_lists_helper(tex_id)
        texture_rows = []

        for u in range(TEX_WIDTH):
            col = []
            for v in range(TEX_HEIGHT):
                col.append(tex_pixels[(v * TEX_WIDTH) + u])

            texture_rows.append((tex_id,u,col))

        con.executemany("""
            INSERT INTO textures_col_based
            VALUES (?,?,?)
        """, texture_rows)

    grouped_build_end = time.perf_counter()

    wall_col_rows = con.sql("""
        SELECT COUNT(*)
        FROM textures_col_based
    """).fetchall()[0][0]

    print(f"WALL column based build time for {texture_count} textures: {grouped_build_end - grouped_build_start} seconds")
    print(f"WALL column based row count for {texture_count} textures: {wall_col_rows}")

    query_wall_col_fixed = """
        SELECT SUM(t.row[s.v + 1]) AS res
        FROM textures_col_based AS t
        JOIN samples_wall_fixed AS s
        ON t.texture_id = s.texture_id
        AND t.col = s.u
    """

    query_wall_col_spread = """
        SELECT SUM(t.row[s.v + 1]) AS res
        FROM textures_col_based AS t
        JOIN samples_wall_spread AS s
        ON t.texture_id = s.texture_id
        AND t.col = s.u
    """

    print()
    print("Calculating WALL COLUMN BASED fixed working set checksum")
    checksum_wall_col_fixed = con.sql(query_wall_col_fixed).fetchall()[0][0]
    print(f"checksum WALL COLUMN BASED fixed working set {checksum_wall_col_fixed}")

    print("Calculating WALL COLUMN BASED spread working set checksum")
    checksum_wall_col_spread = con.sql(query_wall_col_spread).fetchall()[0][0]
    print(f"checksum WALL COLUMN BASED spread working set {checksum_wall_col_spread}")

    benchmark_query(
        con,
        query_wall_col_fixed,
        f"WALL {texture_count} TEXTURES COLUMN BASED FIXED WORKING SET",
    )

    benchmark_query(
        con,
        query_wall_col_spread,
        f"WALL {texture_count} TEXTURES COLUMN BASED SPREAD WORKING SET",
    )


    print()
    print("####################################################################################################")
    print(f"Creating WALL pixel based representation with {texture_count} textures")

    con.execute("""
        CREATE TABLE textures_pixel_based(
            texture_id INTEGER,
            u INTEGER,
            v INTEGER,
            palette_index UTINYINT NOT NULL,
            PRIMARY KEY(texture_id,u,v)
        )
    """)

    pixel_build_start = time.perf_counter()

    con.execute(f"""
        INSERT INTO textures_pixel_based
        SELECT
            t.texture_id,
            t.col AS u,
            CAST(v.i AS INTEGER) AS v,
            t.row[v.i + 1] AS palette_index
        FROM textures_col_based AS t
        CROSS JOIN generate_series(0,{TEX_HEIGHT - 1}) v(i)
    """)

    pixel_build_end = time.perf_counter()

    wall_pixel_rows = con.sql("""
        SELECT COUNT(*)
        FROM textures_pixel_based
    """).fetchall()[0][0]

    print(f"WALL pixel based expansion time for {texture_count} textures: {pixel_build_end - pixel_build_start} seconds")
    print(f"WALL pixel based row count for {texture_count} textures: {wall_pixel_rows}")
    print(f"WALL relational/grouped row count ratio: {wall_pixel_rows / wall_col_rows}")

    query_wall_pixel_fixed = """
        SELECT SUM(p.palette_index) AS res
        FROM textures_pixel_based AS p
        JOIN samples_wall_fixed AS s
        ON p.texture_id = s.texture_id
        AND p.u = s.u
        AND p.v = s.v
    """

    query_wall_pixel_spread = """
        SELECT SUM(p.palette_index) AS res
        FROM textures_pixel_based AS p
        JOIN samples_wall_spread AS s
        ON p.texture_id = s.texture_id
        AND p.u = s.u
        AND p.v = s.v
    """

    print()
    print("Calculating WALL PIXEL BASED fixed working set checksum")
    checksum_wall_pixel_fixed = con.sql(query_wall_pixel_fixed).fetchall()[0][0]
    print(f"checksum WALL PIXEL BASED fixed working set {checksum_wall_pixel_fixed}")
    print(f"checksum WALL COLUMN BASED fixed working set {checksum_wall_col_fixed}")
    assert checksum_wall_pixel_fixed == checksum_wall_col_fixed
    print("WALL fixed working set checksum phase passed")

    print()
    print("Calculating WALL PIXEL BASED spread working set checksum")
    checksum_wall_pixel_spread = con.sql(query_wall_pixel_spread).fetchall()[0][0]
    print(f"checksum WALL PIXEL BASED spread working set {checksum_wall_pixel_spread}")
    print(f"checksum WALL COLUMN BASED spread working set {checksum_wall_col_spread}")
    assert checksum_wall_pixel_spread == checksum_wall_col_spread
    print("WALL spread working set checksum phase passed")

    benchmark_query(
        con,
        query_wall_pixel_fixed,
        f"WALL {texture_count} TEXTURES PIXEL BASED FIXED WORKING SET",
    )

    benchmark_query(
        con,
        query_wall_pixel_spread,
        f"WALL {texture_count} TEXTURES PIXEL BASED SPREAD WORKING SET",
    )

    con.close()


def benchmark_flats(texture_count: int):
    print()
    print()
    print("####################################################################################################")
    print("####################################################################################################")
    print(f"FLATS SCALING BENCHMARK WITH {texture_count} TEXTURES")
    print("####################################################################################################")
    print("####################################################################################################")

    con = duckdb.connect(
        ":memory:",
        config={"threads": 1},
    )

    create_flat_samples_fixed(con)
    create_flat_samples_spread(con,texture_count)

    print()
    print(f"Creating FLATS row based representation with {texture_count} textures")

    con.execute("""
        CREATE TABLE flats_row_based(
            texture_id INTEGER,
            row INTEGER,
            pixels UTINYINT[] NOT NULL,
            PRIMARY KEY(texture_id,row)
        )
    """)

    grouped_build_start = time.perf_counter()

    for texture_id in range(texture_count):
        if texture_id % 50 == 0:
            print(f"Creating FLAT texture {texture_id}/{texture_count}")

        pixels = __create_flats_texture_helper(texture_id)
        texture_rows = []

        for v in range(FLATS_HEIGHT):
            row = []
            for u in range(FLATS_WIDTH):
                row.append(pixels[(v * FLATS_WIDTH) + u])

            texture_rows.append((texture_id,v,row))

        con.executemany("""
            INSERT INTO flats_row_based
            VALUES (?,?,?)
        """, texture_rows)

    grouped_build_end = time.perf_counter()

    flat_row_rows = con.sql("""
        SELECT COUNT(*)
        FROM flats_row_based
    """).fetchall()[0][0]

    print(f"FLATS row based build time for {texture_count} textures: {grouped_build_end - grouped_build_start} seconds")
    print(f"FLATS row based row count for {texture_count} textures: {flat_row_rows}")

    query_flat_row_fixed = """
        SELECT SUM(r.pixels[s.u + 1]) AS res
        FROM flats_row_based AS r
        JOIN samples_flats_fixed AS s
        ON r.texture_id = s.texture_id
        AND r.row = s.v
    """

    query_flat_row_spread = """
        SELECT SUM(r.pixels[s.u + 1]) AS res
        FROM flats_row_based AS r
        JOIN samples_flats_spread AS s
        ON r.texture_id = s.texture_id
        AND r.row = s.v
    """

    print()
    print("Calculating FLATS ROW BASED fixed working set checksum")
    checksum_flat_row_fixed = con.sql(query_flat_row_fixed).fetchall()[0][0]
    print(f"checksum FLATS ROW BASED fixed working set {checksum_flat_row_fixed}")

    print("Calculating FLATS ROW BASED spread working set checksum")
    checksum_flat_row_spread = con.sql(query_flat_row_spread).fetchall()[0][0]
    print(f"checksum FLATS ROW BASED spread working set {checksum_flat_row_spread}")

    benchmark_query(
        con,
        query_flat_row_fixed,
        f"FLATS {texture_count} TEXTURES ROW BASED FIXED WORKING SET",
    )

    benchmark_query(
        con,
        query_flat_row_spread,
        f"FLATS {texture_count} TEXTURES ROW BASED SPREAD WORKING SET",
    )


    print()
    print("####################################################################################################")
    print(f"Creating FLATS pixel based representation with {texture_count} textures")

    con.execute("""
        CREATE TABLE flats_pixel_based(
            texture_id INTEGER,
            u INTEGER,
            v INTEGER,
            palette_index UTINYINT NOT NULL,
            PRIMARY KEY(texture_id,u,v)
        )
    """)

    pixel_build_start = time.perf_counter()

    con.execute(f"""
        INSERT INTO flats_pixel_based
        SELECT
            r.texture_id,
            CAST(u.i AS INTEGER) AS u,
            r.row AS v,
            r.pixels[u.i + 1] AS palette_index
        FROM flats_row_based AS r
        CROSS JOIN generate_series(0,{FLATS_WIDTH - 1}) u(i)
    """)

    pixel_build_end = time.perf_counter()

    flat_pixel_rows = con.sql("""
        SELECT COUNT(*)
        FROM flats_pixel_based
    """).fetchall()[0][0]

    print(f"FLATS pixel based expansion time for {texture_count} textures: {pixel_build_end - pixel_build_start} seconds")
    print(f"FLATS pixel based row count for {texture_count} textures: {flat_pixel_rows}")
    print(f"FLATS relational/grouped row count ratio: {flat_pixel_rows / flat_row_rows}")

    query_flat_pixel_fixed = """
        SELECT SUM(p.palette_index) AS res
        FROM flats_pixel_based AS p
        JOIN samples_flats_fixed AS s
        ON p.texture_id = s.texture_id
        AND p.u = s.u
        AND p.v = s.v
    """

    query_flat_pixel_spread = """
        SELECT SUM(p.palette_index) AS res
        FROM flats_pixel_based AS p
        JOIN samples_flats_spread AS s
        ON p.texture_id = s.texture_id
        AND p.u = s.u
        AND p.v = s.v
    """

    print()
    print("Calculating FLATS PIXEL BASED fixed working set checksum")
    checksum_flat_pixel_fixed = con.sql(query_flat_pixel_fixed).fetchall()[0][0]
    print(f"checksum FLATS PIXEL BASED fixed working set {checksum_flat_pixel_fixed}")
    print(f"checksum FLATS ROW BASED fixed working set {checksum_flat_row_fixed}")
    assert checksum_flat_pixel_fixed == checksum_flat_row_fixed
    print("FLATS fixed working set checksum phase passed")

    print()
    print("Calculating FLATS PIXEL BASED spread working set checksum")
    checksum_flat_pixel_spread = con.sql(query_flat_pixel_spread).fetchall()[0][0]
    print(f"checksum FLATS PIXEL BASED spread working set {checksum_flat_pixel_spread}")
    print(f"checksum FLATS ROW BASED spread working set {checksum_flat_row_spread}")
    assert checksum_flat_pixel_spread == checksum_flat_row_spread
    print("FLATS spread working set checksum phase passed")

    benchmark_query(
        con,
        query_flat_pixel_fixed,
        f"FLATS {texture_count} TEXTURES PIXEL BASED FIXED WORKING SET",
    )

    benchmark_query(
        con,
        query_flat_pixel_spread,
        f"FLATS {texture_count} TEXTURES PIXEL BASED SPREAD WORKING SET",
    )

    con.close()


def main():
    print(f"DuckDB version: {duckdb.__version__}")
    print(f"Texture counts: {TEXTURE_COUNTS}")
    print(f"Samples per benchmark: {NUM_SAMPLES}")
    print(f"Warmup runs: {NUM_WARMUP_RUNS}")
    print(f"Measured runs: {NUM_RUNS}")

    print()
    print("####################################################################################################")
    print("WALL TEXTURE SCALING")
    print("Comparing one LIST per wall column against one row per wall texel")
    print("FIXED WORKING SET touches only the first few textures while the table grows")
    print("SPREAD WORKING SET distributes the samples across all textures in the table")

    for texture_count in TEXTURE_COUNTS:
        benchmark_walls(texture_count)

    print()
    print("####################################################################################################")
    print("FLAT TEXTURE SCALING")
    print("Comparing one LIST per flat row against one row per flat texel")
    print("FIXED WORKING SET touches only the first few textures while the table grows")
    print("SPREAD WORKING SET distributes the samples across all textures in the table")

    for texture_count in TEXTURE_COUNTS:
        benchmark_flats(texture_count)


if __name__ == "__main__":
    main()

