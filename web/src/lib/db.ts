import { Pool, type PoolClient } from "pg";
import { requireEnv } from "./env.ts";

let pool: Pool | undefined;

function getPool(): Pool {
  pool ??= new Pool({ connectionString: requireEnv("APP_DATABASE_URL"), max: 5 });
  return pool;
}

/**
 * Run `fn` in a transaction with row-level security scoped to `userId`.
 * Every query the app makes on behalf of a user goes through this.
 * APP_DATABASE_URL must use the non-superuser `tastepipe_app` role: superusers bypass RLS.
 */
export async function withUser<T>(userId: string, fn: (client: PoolClient) => Promise<T>): Promise<T> {
  const client = await getPool().connect();
  try {
    await client.query("BEGIN");
    await client.query("SELECT set_config('app.user_id', $1, true)", [userId]);
    const result = await fn(client);
    await client.query("COMMIT");
    return result;
  } catch (err) {
    await client.query("ROLLBACK").catch(() => undefined);
    throw err;
  } finally {
    client.release();
  }
}
