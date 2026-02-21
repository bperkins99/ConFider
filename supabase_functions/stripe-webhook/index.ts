import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import Stripe from "https://esm.sh/stripe@11.16.0?target=deno";
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY') as string, {
  apiVersion: '2022-11-15',
  httpClient: Stripe.createFetchHttpClient(),
});

const cryptoProvider = Stripe.createSubtleCryptoProvider();

serve(async (req) => {
  const signature = req.headers.get("Stripe-Signature");
  const body = await req.text();
  let receivedEvent;
  try {
    receivedEvent = await stripe.webhooks.constructEventAsync(
      body,
      signature!,
      Deno.env.get("STRIPE_WEBHOOK_SECRET")!,
      undefined,
      cryptoProvider
    );
  } catch (err) {
    return new Response(err.message, { status: 400 });
  }

  // If this is a successful checkout completion
  if (receivedEvent.type === 'checkout.session.completed') {
    const session = receivedEvent.data.object as Stripe.Checkout.Session;
    
    // The user's Supabase ID should be passed in the clientReferenceId when they click the checkout link
    const userId = session.client_reference_id; 

    if (userId) {
      // Connect to Supabase using the Service Role Key (bypasses RLS to update subscriptions)
      const supabaseAdmin = createClient(
        Deno.env.get('SUPABASE_URL') ?? '',
        Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
      )
      
      // Upgrade the user to the Jail Roster tier based on our SaaS model
      const { error } = await supabaseAdmin
        .from('user_subscriptions')
        .update({ plan_tier: 'Jail Roster Plan', updated_at: new Date().toISOString() })
        .eq('id', userId)
        
      if (error) {
         console.error("DB Update Error:", error);
         return new Response(JSON.stringify({ error: error.message }), { status: 500 });
      }
    }
  }

  return new Response(JSON.stringify({ ok: true }), { status: 200 });
})
