import createClient from 'openapi-fetch'
import type { paths } from './schema'

// Types come only from the generated schema (AD-13). Regenerate with `npm run gen:api:file`.
// Paths in the schema already carry the /api/v1 prefix. The session cookie is sent same-origin.
export const api = createClient<paths>({ baseUrl: '' })
