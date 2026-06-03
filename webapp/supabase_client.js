import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js/+esm'
export const supabase = createClient(
  'SUPABASE_URL_PLACEHOLDER',
  'SUPABASE_ANON_KEY_PLACEHOLDER'
)
