"""Create the HNSW index used for similarity search (cosine distance, <=>).

Safe to re-run (IF NOT EXISTS). Unlike ivfflat, HNSW needs no training data,
so it can be built on an empty or small table and stays accurate as rows are added.

    venv/bin/python -m ingest.create_vector_index
"""
from dotenv import load_dotenv
load_dotenv()
import os, time, psycopg2

def main():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    conn.autocommit = True
    cur = conn.cursor()

    # Session-only settings: the defaults (32MB, 2min) make the build spill to
    # disk and hit the statement timeout. Parallel builds put maintenance_work_mem
    # in shared memory, which Supabase's small instances don't have room for
    # ("could not resize shared memory segment"), so build single-threaded.
    cur.execute("set maintenance_work_mem = '256MB'")
    cur.execute("set max_parallel_maintenance_workers = 0")
    cur.execute("set statement_timeout = 0")

    print("building documents_embedding_hnsw_idx...")
    start = time.time()
    cur.execute("""
        create index if not exists documents_embedding_hnsw_idx
            on documents using hnsw (embedding vector_cosine_ops)
    """)
    print(f"done in {time.time() - start:.0f}s")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
