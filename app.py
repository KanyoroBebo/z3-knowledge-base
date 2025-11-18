import streamlit as st
import csv
import ast
from z3 import *

# --- CONFIGURATION ---
st.set_page_config(page_title="Macadamia Doctor", page_icon="🌰")
st.title("🌰 Dr. Macadamia")

# --- LOAD KNOWLEDGE BASE (Z3 Logic) ---
@st.cache_resource
def load_kb():
    # Initialize Z3 Fixedpoint Engine
    fp = Fixedpoint()
    fp.set(engine='datalog')
    Thing = BitVecSort(32)
    
    # ID Helpers
    str_to_id = {}
    id_to_str = {}
    counter = 1

    def get_id(text):
        nonlocal counter
        if not text: return None
        clean = text.strip().strip("'").strip('"')
        if clean not in str_to_id:
            val = BitVecVal(counter, Thing)
            str_to_id[clean] = val
            id_to_str[counter] = clean
            counter += 1
        return str_to_id[clean]

    def get_name(val):
        try: return id_to_str.get(val.as_long(), str(val))
        except: return str(val)

    # Define Relations
    # Structure: Disease has Symptom, Treatment treats Disease
    has_symptom = Function('has_symptom', Thing, Thing, BoolSort())
    treated_with = Function('treated_with', Thing, Thing, BoolSort())
    
    fp.register_relation(has_symptom)
    fp.register_relation(treated_with)

    # Load Data from CSV
    all_symptoms = set()
    all_diseases = set() # New: Track diseases for the dropdown
    
    try:
        with open('macadamia.csv', mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                disease_name = row['name']
                disease_id = get_id(disease_name)
                all_diseases.add(disease_name)
                
                # Load Symptoms
                if row.get('symptoms'):
                    try:
                        for s in ast.literal_eval(row['symptoms']):
                            fp.fact(has_symptom(disease_id, get_id(s)))
                            all_symptoms.add(s)
                    except: pass
                
                # Load Treatments
                if row.get('treatments'):
                    try:
                        for t in ast.literal_eval(row['treatments']):
                            fp.fact(treated_with(get_id(t), disease_id))
                    except: pass
    except FileNotFoundError:
        return None, None, None, None, None, None, None, None

    # Define Logic Rules
    t, d, s = Consts('t d s', Thing)
    fp.declare_var(t, d, s)
    
    # Rule: A Treatment 't' cures Symptom 's' IF 't' treats Disease 'd' AND 'd' has symptom 's'
    cures_symptom = Function('cures_symptom', Thing, Thing, BoolSort())
    fp.register_relation(cures_symptom)
    fp.rule(cures_symptom(t, s), [treated_with(t, d), has_symptom(d, s)])

    return fp, has_symptom, treated_with, cures_symptom, get_id, get_name, sorted(list(all_symptoms)), sorted(list(all_diseases)), Thing

# APP LOGIC
fp, has_symptom_rel, treated_with_rel, cures_symptom_rel, get_id, get_name, symptoms, diseases, ThingType = load_kb()

if not fp:
    st.error("Error: 'macadamia.csv' file not found.")
    st.stop()

# Helper to extract clean text from Z3 results
def parse_results(ans_obj):
    results = set()
    def collect(expr):
        if is_bv_value(expr): results.add(get_name(expr))
        for child in expr.children(): collect(child)
    collect(ans_obj)
    return sorted(list(results))

# USER INTERFACE
tab1, tab2 = st.tabs(["Symptom Checker", "Disease Lookup"])

# TAB 1: SEARCH BY SYMPTOM
with tab1:
    st.header("Diagnose by Symptom")
    selected_symptom = st.selectbox(
        "I see this symptom:",
        symptoms, 
        index=None, 
        placeholder="Select a symptom..."
        )

    if st.button("Diagnose Problem"):
        st.divider()
        s_id = get_id(selected_symptom)
        
        # DIAGNOSIS (What disease has this symptom?)
        d_var = Const('d', ThingType)
        fp.declare_var(d_var)
        diag_result = fp.query(has_symptom_rel(d_var, s_id))
        
        found_disease = False
        if diag_result == sat:
            diseases_found = parse_results(fp.get_answer())
            for d in diseases_found:
                st.error(f"**Potential Cause:** {d}")
                found_disease = True
        else:
            st.warning("Unknown disease.")

        # PRESCRIPTION (What cures this symptom?)
        if found_disease:
            t_var = Const('t', ThingType)
            fp.declare_var(t_var)
            cure_result = fp.query(cures_symptom_rel(t_var, s_id))
            
            if cure_result == sat:
                treatments = parse_results(fp.get_answer())
                if treatments:
                    st.success(f"**Recommended Treatments:** {', '.join(treatments)}")
                else:
                    st.info("No specific chemical treatment listed.")
            else:
                st.info("No cure found in database.")

# TAB 2: SEARCH BY DISEASE
with tab2:
    st.header("Disease Encyclopedia")
    selected_disease = st.selectbox(
        "Select a Disease or Pest:",
        diseases,
        index=None,
        placeholder="Select a disease..."
        )
    
    if st.button("Get Info"):
        st.divider()
        d_id = get_id(selected_disease)
        
        #  SYMPTOMS (Query: has_symptom(SelectedDisease, s))
        s_var = Const('s', ThingType)
        fp.declare_var(s_var)
        sym_result = fp.query(has_symptom_rel(d_id, s_var))
        
        st.subheader("Symptoms")
        if sym_result == sat:
            found_symptoms = parse_results(fp.get_answer())
            for sym in found_symptoms:
                st.markdown(f"- {sym}")
        else:
            st.write("No symptoms recorded.")

        # GET TREATMENTS (Query: treated_with(t, SelectedDisease))
        t_var = Const('t', ThingType)
        fp.declare_var(t_var)
        treat_result = fp.query(treated_with_rel(t_var, d_id))
        
        st.subheader("Treatments")
        if treat_result == sat:
            found_treatments = parse_results(fp.get_answer())
            for treat in found_treatments:
                st.success(f"{treat}")
        else:
            st.warning("No treatments recorded.")