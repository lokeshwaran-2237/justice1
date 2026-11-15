"""Rule-based legal awareness assistant for Justice.
General information only - not legal advice."""

KB = [
    {"k": ["arrest", "police", "custody", "detain", "lock up"], "area": "Criminal",
     "text": "If you or a family member is arrested:\n- You must be told the grounds of arrest.\n- You can consult and be defended by a lawyer of your choice (Article 22).\n- You must be produced before a magistrate within 24 hours (excluding travel time).\n- You may stay silent and inform a relative or friend.\n- In an emergency call 112."},
    {"k": ["bail", "remand", "anticipatory"], "area": "Criminal",
     "text": "Bail is a right in bailable offences. For non-bailable offences the magistrate or sessions court decides. If you fear arrest, a lawyer can apply for anticipatory bail. If you cannot afford a lawyer, free legal aid is available (15100)."},
    {"k": ["fir", "complaint", "refuse", "file a case"], "area": "Criminal",
     "text": "For a cognizable offence the police must register an FIR and you can ask for a free copy. If they refuse, send the complaint in writing to the Superintendent of Police or approach the Magistrate. A Zero FIR can be filed at any police station."},
    {"k": ["domestic", "dowry", "husband", "harass", "protection order", "violence", "abuse"], "area": "Family",
     "text": "Under the Protection of Women from Domestic Violence Act, 2005 a woman can seek a protection order, the right to stay in the shared home, monetary relief and custody orders. Contact a Protection Officer, a lawyer or the magistrate court. Helplines: 181 (women), 112 (emergency)."},
    {"k": ["divorce", "maintenance", "custody", "marriage", "alimony", "child"], "area": "Family",
     "text": "Family matters are heard by Family Courts. Mutual-consent divorce is faster; contested divorce needs grounds under the applicable personal law. Spouses and children can claim maintenance. A family-law advocate at your court is the best first step."},
    {"k": ["consumer", "refund", "defective", "product", "warranty", "service", "cheated"], "area": "Consumer",
     "text": "Consumer Protection Act, 2019: first send a written complaint or legal notice to the seller. If unresolved, file with the District Consumer Commission (claims up to Rs 50 lakh), online through e-Daakhil. National Consumer Helpline: 1915."},
    {"k": ["property", "land", "tenant", "rent", "landlord", "evict", "patta", "sale deed", "encroach"], "area": "Property",
     "text": "Verify the title deed chain, encumbrance certificate and registration before buying property. A landlord cannot evict a tenant by force; it needs a legal process. Keep all agreements and receipts."},
    {"k": ["cyber", "online fraud", "upi", "scam", "hack", "morph", "otp"], "area": "Cyber",
     "text": "Act fast: call 1930 or report at cybercrime.gov.in, and inform your bank immediately to try to freeze the transaction. Save screenshots, transaction IDs and messages as evidence."},
    {"k": ["salary", "wages", "job", "employer", "terminated", "labour", "pf", "fired"], "area": "Labour",
     "text": "Unpaid wages or wrongful termination can be raised with the Labour Commissioner or Labour Court. Keep your appointment letter, payslips and bank statements. PF complaints go to the EPFO grievance portal."},
    {"k": ["rti", "right to information"], "area": "Civil",
     "text": "RTI Act, 2005: apply in writing to the Public Information Officer with a Rs 10 fee. A reply is due within 30 days; if unsatisfied you can file a first appeal."},
    {"k": ["free", "afford", "legal aid", "poor", "cost", "money"], "area": "",
     "text": "Free legal aid: the National Legal Services Authority (toll-free 15100) and the District Legal Services Authority at your district court provide free lawyers to women, children, SC/ST persons, persons in custody and those under the income limit."},
    {"k": ["verify", "bar council", "fake", "genuine", "trust"], "area": "",
     "text": "On Justice an advocate is listed only after the Bar Council approval letter and enrollment number are verified by an administrator. You can also check any advocate's enrollment number with the State Bar Council."},
]

FALLBACK = ("I can help with arrest and bail, FIR, domestic violence, divorce and custody, consumer "
            "complaints, property and tenancy, cyber fraud, labour issues, RTI and free legal aid. "
            "Please rephrase your question using one of these topics.")
DISCLAIMER = "\n\nThis is general information, not legal advice."


def answer(message: str) -> dict:
    """Return {"reply": str, "area": str|None} for the best-matching topic."""
    m = (message or "").lower()
    best, score = None, 0
    for e in KB:
        s = sum(1 for k in e["k"] if k in m)
        if s > score:
            best, score = e, s
    if not best:
        return {"reply": FALLBACK, "area": None}
    return {"reply": best["text"] + DISCLAIMER, "area": best["area"] or None}
