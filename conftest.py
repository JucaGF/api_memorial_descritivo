"""Global test configuration.

Sets Supabase and LLM env vars to empty strings before any module is imported.
load_dotenv(override=False) will not overwrite existing env vars, so the
filesystem backend and no-LLM behavior stay active during tests.
"""
import os

os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_KEY"] = ""
os.environ["SUPABASE_SECRET_KEY"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
os.environ["USE_LLM_EXTRACTION"] = ""
