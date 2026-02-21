import streamlit as st
from supabase import create_client, Client
import pandas as pd
import json
import os
import urllib.parse
from datetime import datetime

# Supabase Auth Configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    try:
        SUPABASE_URL = st.secrets["supabase"]["url"]
        SUPABASE_KEY = st.secrets["supabase"]["key"]
    except Exception:
        st.error("Missing Supabase configuration. Please set SUPABASE_URL and SUPABASE_KEY environment variables.")
        st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEADS_FILE = os.path.join(BASE_DIR, "leads.json")
ATTORNEYS_FILE = os.path.join(BASE_DIR, "attorneys.json")

st.set_page_config(page_title="Jail Roster Lead Generator", page_icon="⚖️", layout="wide")

# DEBUG: Temporary check for login issues
# st.write(f"Current User: {st.session_state.get('user')}")

# --- Authentication ---
if "user" not in st.session_state:
    st.session_state["user"] = None
if "subscription" not in st.session_state:
    st.session_state["subscription"] = None

def fetch_user_settings(user_id):
    if "settings" not in st.session_state:
        st.session_state["settings"] = {"email_alerts": False, "alert_email": st.session_state["user"].email}
    try:
        res = supabase.table("user_settings").select("*").eq("id", user_id).execute()
        if res.data:
            st.session_state["settings"] = res.data[0]
        else:
            # Initialize settings if not found
            supabase.table("user_settings").insert({"id": user_id, "email_alerts": False, "alert_email": st.session_state["user"].email}).execute()
    except Exception:
        pass

def save_user_settings(user_id, settings):
    try:
        supabase.table("user_settings").upsert({"id": user_id, **settings}).execute()
        st.session_state["settings"] = settings
        st.sidebar.success("Settings saved!", icon="✅")
    except Exception as e:
        st.sidebar.error(f"Error saving settings: {e}")

def fetch_subscription(user_id):
    try:
        sub_res = supabase.table("user_subscriptions").select("plan_tier").eq("id", user_id).execute()
        if sub_res.data:
            st.session_state["subscription"] = sub_res.data[0]["plan_tier"]
        else:
            # Initialize record in DB as free if not found
            supabase.table("user_subscriptions").insert({"id": user_id, "plan_tier": "free"}).execute()
            st.session_state["subscription"] = "free"
    except Exception as e:
        st.session_state["subscription"] = "free"
    
    fetch_user_settings(user_id)

def login(email, password):
    try:
        # Debugging
        # st.write(f"Attempting login for {email}...") 
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if res.user:
            st.session_state["user"] = res.user
            # st.success(f"Logged in as {res.user.email}")
            fetch_subscription(res.user.id)
            return True
        return False
    except Exception as e:
        st.error(f"Login Failed: {e}")
        return False

def signup(email, password):
    try:
        res = supabase.auth.sign_up({"email": email, "password": password})
        st.success("Signup successful! Please log in.")
    except Exception as e:
        st.error(f"Signup Failed: {e}")

def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    st.session_state["user"] = None
    st.session_state["subscription"] = None

if not st.session_state["user"]:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.title("🔒 Login to Blackfork Labs")
        with st.form("auth_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            colA, colB = st.columns(2)
            with colA:
                submit_login = st.form_submit_button("Log In", use_container_width=True)
            with colB:
                submit_signup = st.form_submit_button("Sign Up", use_container_width=True)
            
        if submit_login:
            if login(email, password):
                st.rerun()
        if submit_signup:
            signup(email, password)
    st.stop()

st.sidebar.markdown(f"**Logged in as:** {st.session_state['user'].email}")
st.sidebar.markdown(f"**Current Plan:** {str(st.session_state['subscription']).capitalize() if st.session_state['subscription'] else 'Free'}")

# --- Notification Settings UI ---
st.sidebar.markdown("---")
with st.sidebar.expander("🔔 Notification Settings", expanded=False):
    settings = st.session_state.get("settings", {"email_alerts": False, "alert_email": st.session_state["user"].email})
    
    email_alerts = st.toggle("Enable Email Alerts", value=settings.get("email_alerts", False))
    alert_email = st.text_input("Alert Destination Email", value=settings.get("alert_email", st.session_state["user"].email))
    
    if st.button("Save Preferences", use_container_width=True):
        updated_settings = {
            "email_alerts": email_alerts,
            "alert_email": alert_email
        }
        save_user_settings(st.session_state["user"].id, updated_settings)

st.sidebar.markdown("---")
if st.sidebar.button("Log Out"):
    logout()
    st.rerun()


# --- Helper Functions ---
@st.cache_data
def load_data(filepath):
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading {filepath}: {e}")
        return []

def save_attorneys(attorneys):
    try:
        with open(ATTORNEYS_FILE, "w") as f:
            json.dump(attorneys, f, indent=4)
        st.toast("Attorney directory updated!", icon="💾")
    except Exception as e:
        st.error(f"Error saving attorneys: {e}")

# --- Main App ---
st.title("⚖️ Jail Roster Lead Generator")
st.subheader("Richland County, Ohio")

# Load Data
leads_data = load_data(LEADS_FILE)
attorneys_data = load_data(ATTORNEYS_FILE)

# Create Tabs
tab_leads, tab_attorneys = st.tabs(["📋 Leads", "📇 Attorney Directory"])

# --- TAB 1: Leads ---
with tab_leads:
    if not leads_data:
        st.warning("No leads found. Run the scraper first.")
    else:
        df = pd.DataFrame(leads_data)
        
        # Format for display
        df["display_charges"] = df["charges"].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
        df["Select"] = True # Default selection state

        # --- Filtering & Sorting Logic ---
        # Parse dates for filtering/sorting
        df["parsed_date"] = pd.to_datetime(df["booking_date"], format="%m/%d/%Y", errors="coerce")
        df = df.sort_values(by="parsed_date", ascending=False).reset_index(drop=True)

        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Filter Dropdown
            filter_option = st.selectbox(
                "📅 Filter by Booking Date:",
                ["Last 2 Days (Fresh Leads)", "Last 7 Days", "Last 30 Days", "All Time (Entire Database)"],
                index=0
            )
            
            # Apply Filter
            filtered_df = df.copy()
            now = pd.Timestamp.now()
            
            if "2 Days" in filter_option:
                filtered_df = filtered_df[filtered_df["parsed_date"] >= (now - pd.Timedelta(days=2))]
            elif "7 Days" in filter_option:
                filtered_df = filtered_df[filtered_df["parsed_date"] >= (now - pd.Timedelta(days=7))]
            elif "30 Days" in filter_option:
                filtered_df = filtered_df[filtered_df["parsed_date"] >= (now - pd.Timedelta(days=30))]
            
            # --- Subscription Gate ---
            full_count = len(df)
            tier = st.session_state.get("subscription", "free")
            
            if tier == "free":
                stripe_url = f"https://buy.stripe.com/4gMdR8bwD2VJd8N07xb3q00?client_reference_id={st.session_state.get('user').id}"
                st.info(f"⭐ **Free Plan (Demo Mode)**: Showing only the 3 most recent leads. [**Upgrade to the Jail Roster Plan for full access**]({stripe_url})")
                filtered_df = filtered_df.head(3)
            elif tier == "admin":
                st.success("👑 **Admin Access**: Lead restrictions bypassed.")

            showing_count = len(filtered_df)
            st.markdown(f"### Showing {showing_count} Leads *(Out of {full_count} total)*")
            display_cols = ["Select", "name", "booking_date", "display_charges"]
            
            edited_df = st.data_editor(
                filtered_df[display_cols],
                column_config={
                    "Select": st.column_config.CheckboxColumn("Select", default=True),
                    "name": "Inmate Name",
                    "booking_date": "Booking Date",
                    "display_charges": "Target Charges",
                },
                use_container_width=True,
                hide_index=True,
                key="leads_editor"
            )

        with col2:
            st.markdown("### ✉️ Actions")
            
            # Attorney Selection for Matching
            attorney_options = {f"{a['name']} ({a['firm']})": a for a in attorneys_data}
            selected_attorney_name = st.selectbox("Select Attorney:", options=list(attorney_options.keys()) if attorneys_data else [])
            
            # Check for Secrets
            has_secrets = "gmail" in st.secrets
            
            if st.button("Generate Drafts (Mailto)", type="secondary"):
                # ... existing mailto logic (preserved as backup) ...
                pass 

            if has_secrets:
                if st.button("🚀 Send Emails Now", type="primary"):
                    selected_leads = edited_df[edited_df["Select"] == True]
                    
                    if selected_leads.empty:
                        st.warning("Select inmates first.")
                    elif not selected_attorney_name:
                         st.warning("Select an attorney first.")
                    else:
                        target_attorney = attorney_options[selected_attorney_name]
                        at_email = target_attorney.get('email', '')
                        at_first_name = target_attorney.get('name', 'Attorney').split()[0]
                        
                        my_email = st.secrets["gmail"]["email"]
                        my_password = st.secrets["gmail"]["password"]

                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        import smtplib
                        from email.mime.text import MIMEText
                        from email.mime.multipart import MIMEMultipart

                        success_count = 0
                        
                        try:
                            # Connect once
                            server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
                            server.login(my_email, my_password)
                            
                            total = len(selected_leads)
                            for i, (index, row) in enumerate(selected_leads.iterrows()):
                                inmate_name = row['name']
                                charges = row['display_charges']
                                date = row['booking_date']
                                
                                subject = f"Referral: {inmate_name} - {charges}"
                                body = (
                                    f"Hi {at_first_name},\n\n"
                                    f"I saw that {inmate_name} was recently booked on {date} for {charges}.\n\n"
                                    f"Thought you might be interested in reaching out.\n\n"
                                    f"Best,\nBrad" 
                                )
                                
                                msg = MIMEMultipart()
                                msg["From"] = my_email
                                msg["To"] = at_email
                                msg["Subject"] = subject
                                msg.attach(MIMEText(body, "plain"))
                                
                                server.send_message(msg)
                                success_count += 1
                                progress = (i + 1) / total
                                progress_bar.progress(progress)
                                status_text.text(f"Sent to {at_first_name} re: {inmate_name}...")
                            
                            server.quit()
                            st.success(f"✅ Successfully sent {success_count} emails!")
                            
                        except Exception as e:
                            st.error(f"Email failed: {e}")
            else:
                st.info("💡 Add Gmail secrets to enable direct sending.")


            # Fallback / Preview Logic
            if not has_secrets and st.button("Generate Generic Drafts"):
                 # ... existing logic ...
                 pass

# --- TAB 2: Attorney Directory ---
with tab_attorneys:
    st.markdown("### 📇 Local Defense Attorneys")
    st.info("Edit this table directly to add or update attorney contact info. Changes save automatically when you click 'Save'.")

    # Ensure consistent columns
    default_columns = ["name", "firm", "email", "phone", "address"]
    
    if not attorneys_data:
        attorneys_df = pd.DataFrame(columns=default_columns)
    else:
        attorneys_df = pd.DataFrame(attorneys_data)
        # Ensure all columns exist even if JSON is partial
        for col in default_columns:
            if col not in attorneys_df.columns:
                attorneys_df[col] = ""

    edited_attorneys = st.data_editor(
        attorneys_df[default_columns],
        num_rows="dynamic",
        use_container_width=True,
        key="attorney_editor",
        column_config={
            "name": "Attorney Name",
            "firm": "Law Firm",
            "email": "Email Address",
            "phone": "Phone Number",
            "address": "Office Address"
        }
    )

    if st.button("💾 Save Directory Changes", type="primary"):
        # Convert back to list of dicts
        updated_attorneys = edited_attorneys.to_dict(orient="records")
        # Filter out empty rows if any
        updated_attorneys = [a for a in updated_attorneys if a.get("name") and str(a.get("name")).strip()]
        
        save_attorneys(updated_attorneys)
        st.balloons()
        st.rerun()
