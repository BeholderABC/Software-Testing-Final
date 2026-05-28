import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st


OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


SAMPLE_REQUIREMENTS = """REQ-001: The system shall display all products with name, description, price, and stock.
REQ-002: The system shall allow users to view product details by product ID.
REQ-003: The system shall allow admin users to create a new product with name, description, price, and stock.
REQ-004: The system shall allow admin users to update an existing product.
REQ-005: The system shall allow admin users to delete a product.
REQ-006: The system shall allow users to create an order with one or more products.
REQ-007: The system shall reject an order if the items array is empty.
REQ-008: The system shall reject an order if customer information is missing.
REQ-009: The system shall reject an order if requested quantity exceeds available stock.
REQ-010: The system shall automatically reduce product stock after a successful order.
REQ-011: The system shall allow users to view order details by order ID.
REQ-012: The system shall allow admin users to update order status to pending, completed, or cancelled."""


def parse_requirements(raw_text):
    rows = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        if ":" in line:
            req_id, req_text = line.split(":", 1)
            req_id = req_id.strip()
            req_text = req_text.strip()
        else:
            req_id = f"REQ-{len(rows) + 1:03d}"
            req_text = line

        lower = req_text.lower()

        if "order" in lower or "stock" in lower or "customer" in lower:
            target_module = "Order Processing"
        elif "product" in lower:
            target_module = "Product Management"
        else:
            target_module = "General"

        input_fields = []
        if "product" in lower:
            input_fields.append("product_id")
        if "quantity" in lower or "stock" in lower:
            input_fields.append("quantity")
            input_fields.append("stock")
        if "customer" in lower:
            input_fields.extend(["customer_name", "customer_phone", "customer_address"])
        if "status" in lower:
            input_fields.append("status")

        if "exceeds available stock" in lower:
            data_ranges = "quantity > stock"
            conditions = "insufficient stock"
            expected_action = "reject order and return 400 Bad Request"
        elif "empty" in lower:
            data_ranges = "items length = 0"
            conditions = "empty items array"
            expected_action = "reject order and return 400 Bad Request"
        elif "missing" in lower:
            data_ranges = "required field is null or empty"
            conditions = "missing required customer information"
            expected_action = "reject request and return 400 Bad Request"
        elif "reduce product stock" in lower:
            data_ranges = "stock after order = original stock - ordered quantity"
            conditions = "successful order"
            expected_action = "update product stock"
        elif "status" in lower:
            data_ranges = "status in [pending, completed, cancelled]"
            conditions = "valid order status update"
            expected_action = "update order status"
        else:
            data_ranges = "valid input range"
            conditions = "valid request"
            expected_action = "return successful response"

        rows.append({
            "requirement_id": req_id,
            "raw_requirement": req_text,
            "input_fields": ", ".join(input_fields),
            "data_ranges": data_ranges,
            "conditions": conditions,
            "expected_action": expected_action,
            "target_module": target_module,
        })

    return pd.DataFrame(rows)


def analyze_risk(requirements_df):
    rows = []
    for _, row in requirements_df.iterrows():
        text = row["raw_requirement"].lower()
        module = row["target_module"]

        business_impact = 3
        failure_probability = 2
        complexity = 2
        user_frequency = 2

        if "order" in text:
            business_impact = 5
            user_frequency = 5
        if "stock" in text:
            business_impact = 5
            complexity = 4
        if "reject" in text or "missing" in text or "exceeds" in text:
            failure_probability = 4
        if "status" in text:
            complexity = 3
        if module == "Product Management":
            business_impact = max(business_impact, 3)

        risk_score = business_impact + failure_probability + complexity + user_frequency

        if risk_score >= 15:
            priority = "High"
        elif risk_score >= 10:
            priority = "Medium"
        else:
            priority = "Low"

        rows.append({
            "requirement_id": row["requirement_id"],
            "target_module": module,
            "business_impact": business_impact,
            "failure_probability": failure_probability,
            "complexity": complexity,
            "user_frequency": user_frequency,
            "risk_score": risk_score,
            "priority": priority,
            "risk_reason": build_risk_reason(row["raw_requirement"], priority),
        })

    return pd.DataFrame(rows)


def build_risk_reason(requirement_text, priority):
    text = requirement_text.lower()
    if "order" in text and "stock" in text:
        return "Order and stock logic directly affects core business correctness."
    if "order" in text:
        return "Order processing is a core business workflow."
    if "reject" in text or "missing" in text:
        return "Invalid input handling affects reliability and user experience."
    if "product" in text:
        return "Product data affects browsing and management functions."
    return f"Priority classified as {priority} based on impact and complexity."


def generate_coverage_items(requirements_df, risk_df):
    rows = []
    for _, req in requirements_df.iterrows():
        risk = risk_df[risk_df["requirement_id"] == req["requirement_id"]].iloc[0]
        priority = risk["priority"]
        text = req["raw_requirement"].lower()

        rows.append({
            "coverage_item_id": f"CI-{len(rows) + 1:03d}",
            "requirement_id": req["requirement_id"],
            "target_module": req["target_module"],
            "coverage_item": f"Validate: {req['expected_action']}",
            "coverage_strategy": "Equivalence Partitioning",
            "priority": priority,
        })

        if priority in ["High", "Medium"]:
            rows.append({
                "coverage_item_id": f"CI-{len(rows) + 1:03d}",
                "requirement_id": req["requirement_id"],
                "target_module": req["target_module"],
                "coverage_item": f"Boundary validation for {req['data_ranges']}",
                "coverage_strategy": "Boundary Value Analysis",
                "priority": priority,
            })

        if "order" in text or "stock" in text or "missing" in text or "reject" in text:
            rows.append({
                "coverage_item_id": f"CI-{len(rows) + 1:03d}",
                "requirement_id": req["requirement_id"],
                "target_module": req["target_module"],
                "coverage_item": "Decision combinations for valid/invalid product, quantity, stock, and customer information",
                "coverage_strategy": "Decision Table Testing",
                "priority": priority,
            })

    return pd.DataFrame(rows)


def generate_test_cases(requirements_df, risk_df, coverage_df):
    rows = []

    for _, cov in coverage_df.iterrows():
        req = requirements_df[requirements_df["requirement_id"] == cov["requirement_id"]].iloc[0]
        risk = risk_df[risk_df["requirement_id"] == cov["requirement_id"]].iloc[0]

        base = {
            "requirement_id": req["requirement_id"],
            "target_module": req["target_module"],
            "risk_priority": risk["priority"],
            "testing_technique": cov["coverage_strategy"],
            "coverage_item": cov["coverage_item"],
            "precondition": "The Mini E-Commerce backend is running and test data exists.",
            "traceability": f"{req['requirement_id']} -> {cov['coverage_item_id']}",
        }

        technique = cov["coverage_strategy"]
        text = req["raw_requirement"].lower()

        if "create an order" in text or "successful order" in text or "reduce product stock" in text:
            rows.extend(order_success_cases(base))
        elif "exceeds available stock" in text or "stock" in text:
            rows.extend(stock_boundary_cases(base))
        elif "missing" in text or "empty" in text:
            rows.extend(order_invalid_input_cases(base))
        elif "status" in text:
            rows.extend(order_status_cases(base))
        elif "product" in text:
            rows.extend(product_cases(base, text))
        else:
            rows.append(make_case(base, "General valid request", "valid input", "Send valid request", "Successful response"))

    for idx, row in enumerate(rows, start=1):
        row["test_case_id"] = f"TC-{idx:03d}"

    columns = [
        "test_case_id",
        "requirement_id",
        "target_module",
        "risk_priority",
        "testing_technique",
        "coverage_item",
        "precondition",
        "test_data",
        "steps",
        "expected_result",
        "traceability",
    ]
    return pd.DataFrame(rows)[columns]


def make_case(base, title, test_data, steps, expected_result):
    case = base.copy()
    case.update({
        "test_data": test_data,
        "steps": steps,
        "expected_result": expected_result,
    })
    return case


def order_success_cases(base):
    return [
        make_case(
            base,
            "Create valid order",
            '{"items":[{"product_id":1,"quantity":1}],"customer_name":"John Doe","customer_phone":"1234567890","customer_address":"123 Main St"}',
            "POST /api/orders/create/ with valid product, quantity, and customer information.",
            "Order is created with status 201 and product stock is reduced."
        ),
        make_case(
            base,
            "Create multi-item order",
            '{"items":[{"product_id":1,"quantity":1},{"product_id":2,"quantity":1}],"customer_name":"John Doe","customer_phone":"1234567890","customer_address":"123 Main St"}',
            "POST /api/orders/create/ with multiple valid products.",
            "Order is created and stock is reduced for all ordered products."
        ),
    ]


def stock_boundary_cases(base):
    return [
        make_case(
            base,
            "Quantity equals available stock",
            '{"items":[{"product_id":1,"quantity":5}],"customer_name":"John Doe","customer_phone":"1234567890","customer_address":"123 Main St"}',
            "Set product stock to 5, then order quantity 5.",
            "Order is created with status 201 and stock becomes 0."
        ),
        make_case(
            base,
            "Quantity exceeds available stock",
            '{"items":[{"product_id":1,"quantity":6}],"customer_name":"John Doe","customer_phone":"1234567890","customer_address":"123 Main St"}',
            "Set product stock to 5, then order quantity 6.",
            "System returns 400 Bad Request with insufficient stock error."
        ),
        make_case(
            base,
            "Quantity is zero",
            '{"items":[{"product_id":1,"quantity":0}],"customer_name":"John Doe","customer_phone":"1234567890","customer_address":"123 Main St"}',
            "POST /api/orders/create/ with quantity 0.",
            "System rejects the request with 400 Bad Request."
        ),
    ]


def order_invalid_input_cases(base):
    return [
        make_case(
            base,
            "Empty items array",
            '{"items":[],"customer_name":"John Doe","customer_phone":"1234567890","customer_address":"123 Main St"}',
            "POST /api/orders/create/ with empty items array.",
            "System returns 400 Bad Request."
        ),
        make_case(
            base,
            "Missing customer name",
            '{"items":[{"product_id":1,"quantity":1}],"customer_phone":"1234567890","customer_address":"123 Main St"}',
            "POST /api/orders/create/ without customer_name.",
            "System returns 400 Bad Request."
        ),
        make_case(
            base,
            "Invalid product ID",
            '{"items":[{"product_id":99999,"quantity":1}],"customer_name":"John Doe","customer_phone":"1234567890","customer_address":"123 Main St"}',
            "POST /api/orders/create/ with non-existing product_id.",
            "System returns 400 Bad Request."
        ),
    ]


def order_status_cases(base):
    return [
        make_case(
            base,
            "Update order status to completed",
            '{"status":"completed"}',
            "PATCH /api/orders/1/ with status completed.",
            "Order status is updated successfully."
        ),
        make_case(
            base,
            "Update order status to invalid value",
            '{"status":"unknown"}',
            "PATCH /api/orders/1/ with invalid status.",
            "System rejects the invalid status."
        ),
    ]


def product_cases(base, text):
    if "display" in text or "view" in text:
        return [
            make_case(
                base,
                "Get all products",
                "No request body",
                "GET /api/products/",
                "System returns product list with id, name, description, price, and stock."
            ),
            make_case(
                base,
                "Get product details by valid ID",
                "product_id = 1",
                "GET /api/products/1/",
                "System returns selected product details."
            ),
            make_case(
                base,
                "Get product details by invalid ID",
                "product_id = 99999",
                "GET /api/products/99999/",
                "System returns 404 Not Found."
            ),
        ]

    return [
        make_case(
            base,
            "Create or update product with valid data",
            '{"name":"New Product","description":"Product description","price":"39.99","stock":50}',
            "Send valid product management request.",
            "System saves product data successfully."
        ),
        make_case(
            base,
            "Product with invalid price",
            '{"name":"New Product","description":"Product description","price":"-1","stock":50}',
            "Send product request with negative price.",
            "System rejects invalid product data."
        ),
    ]


def export_results(requirements_df, risk_df, coverage_df, test_cases_df):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    paths = {
        "structured_requirements_csv": os.path.join(OUTPUT_DIR, f"structured_requirements_{timestamp}.csv"),
        "risk_analysis_csv": os.path.join(OUTPUT_DIR, f"risk_analysis_{timestamp}.csv"),
        "coverage_items_csv": os.path.join(OUTPUT_DIR, f"coverage_items_{timestamp}.csv"),
        "test_cases_csv": os.path.join(OUTPUT_DIR, f"test_cases_{timestamp}.csv"),
        "test_cases_json": os.path.join(OUTPUT_DIR, f"test_cases_{timestamp}.json"),
        "excel": os.path.join(OUTPUT_DIR, f"AutoTestDesign_Output_{timestamp}.xlsx"),
    }

    requirements_df.to_csv(paths["structured_requirements_csv"], index=False, encoding="utf-8-sig")
    risk_df.to_csv(paths["risk_analysis_csv"], index=False, encoding="utf-8-sig")
    coverage_df.to_csv(paths["coverage_items_csv"], index=False, encoding="utf-8-sig")
    test_cases_df.to_csv(paths["test_cases_csv"], index=False, encoding="utf-8-sig")

    with open(paths["test_cases_json"], "w", encoding="utf-8") as f:
        json.dump(test_cases_df.to_dict(orient="records"), f, indent=2, ensure_ascii=False)

    with pd.ExcelWriter(paths["excel"], engine="openpyxl") as writer:
        requirements_df.to_excel(writer, sheet_name="Requirements", index=False)
        risk_df.to_excel(writer, sheet_name="Risk Analysis", index=False)
        coverage_df.to_excel(writer, sheet_name="Coverage Items", index=False)
        test_cases_df.to_excel(writer, sheet_name="Test Cases", index=False)

    return paths


st.set_page_config(page_title="AutoTestDesign Tool", layout="wide")

st.title("AI-driven AutoTestDesign Tool")
st.caption("Requirement Analysis → Risk Analysis → Coverage Design → Test Case Generation → Human Review → Export")

st.sidebar.header("Workflow")
page = st.sidebar.radio(
    "Choose step",
    [
        "1. Requirement Input",
        "2. Requirement Structuring",
        "3. Risk Analysis",
        "4. Coverage Items",
        "5. Test Cases",
        "6. Export",
        "7. Evidence Checklist",
    ]
)

if "raw_requirements" not in st.session_state:
    st.session_state.raw_requirements = SAMPLE_REQUIREMENTS

if page == "1. Requirement Input":
    st.header("1. Requirement Input")
    st.write("Target Application: Mini-E-Commerce-System")
    st.write("Main modules: Product Management, Order Processing, Stock Management, Order Status Management.")

    use_sample = st.checkbox("Use built-in Mini-E-Commerce-System sample requirements", value=True)

    if use_sample:
        st.session_state.raw_requirements = SAMPLE_REQUIREMENTS

    uploaded = st.file_uploader("Upload CSV with requirements", type=["csv"])
    if uploaded is not None:
        uploaded_df = pd.read_csv(uploaded)
        if "raw_requirement" in uploaded_df.columns:
            lines = []
            for i, row in uploaded_df.iterrows():
                req_id = row.get("requirement_id", f"REQ-{i + 1:03d}")
                lines.append(f"{req_id}: {row['raw_requirement']}")
            st.session_state.raw_requirements = "\n".join(lines)

    st.session_state.raw_requirements = st.text_area(
        "Requirement text",
        value=st.session_state.raw_requirements,
        height=300
    )

    if st.button("Parse Requirements"):
        st.session_state.requirements_df = parse_requirements(st.session_state.raw_requirements)
        st.success("Requirements parsed. Go to Step 2.")

elif page == "2. Requirement Structuring":
    st.header("2. Requirement Structuring")
    if "requirements_df" not in st.session_state:
        st.session_state.requirements_df = parse_requirements(st.session_state.raw_requirements)

    st.write("You can review and revise structured requirements here.")
    st.session_state.requirements_df = st.data_editor(
        st.session_state.requirements_df,
        use_container_width=True,
        num_rows="dynamic"
    )

elif page == "3. Risk Analysis":
    st.header("3. Risk Analysis and Prioritization")
    if "requirements_df" not in st.session_state:
        st.session_state.requirements_df = parse_requirements(st.session_state.raw_requirements)

    if st.button("Generate Risk Analysis"):
        st.session_state.risk_df = analyze_risk(st.session_state.requirements_df)

    if "risk_df" not in st.session_state:
        st.session_state.risk_df = analyze_risk(st.session_state.requirements_df)

    st.write("You can manually adjust risk score and priority.")
    st.session_state.risk_df = st.data_editor(
        st.session_state.risk_df,
        use_container_width=True,
        num_rows="dynamic"
    )

elif page == "4. Coverage Items":
    st.header("4. Coverage Item Identification and Strategy")
    if "requirements_df" not in st.session_state:
        st.session_state.requirements_df = parse_requirements(st.session_state.raw_requirements)
    if "risk_df" not in st.session_state:
        st.session_state.risk_df = analyze_risk(st.session_state.requirements_df)

    if st.button("Generate Coverage Items"):
        st.session_state.coverage_df = generate_coverage_items(
            st.session_state.requirements_df,
            st.session_state.risk_df
        )

    if "coverage_df" not in st.session_state:
        st.session_state.coverage_df = generate_coverage_items(
            st.session_state.requirements_df,
            st.session_state.risk_df
        )

    st.write("This section supports human-in-the-loop review. You can revise coverage items and strategies.")
    st.session_state.coverage_df = st.data_editor(
        st.session_state.coverage_df,
        use_container_width=True,
        num_rows="dynamic"
    )

elif page == "5. Test Cases":
    st.header("5. Test Cases and Traceability")
    if "requirements_df" not in st.session_state:
        st.session_state.requirements_df = parse_requirements(st.session_state.raw_requirements)
    if "risk_df" not in st.session_state:
        st.session_state.risk_df = analyze_risk(st.session_state.requirements_df)
    if "coverage_df" not in st.session_state:
        st.session_state.coverage_df = generate_coverage_items(
            st.session_state.requirements_df,
            st.session_state.risk_df
        )

    if st.button("Generate / Regenerate Test Cases"):
        st.session_state.test_cases_df = generate_test_cases(
            st.session_state.requirements_df,
            st.session_state.risk_df,
            st.session_state.coverage_df
        )

    if "test_cases_df" not in st.session_state:
        st.session_state.test_cases_df = generate_test_cases(
            st.session_state.requirements_df,
            st.session_state.risk_df,
            st.session_state.coverage_df
        )

    st.write("You can revise generated test cases before export.")
    st.session_state.test_cases_df = st.data_editor(
        st.session_state.test_cases_df,
        use_container_width=True,
        num_rows="dynamic"
    )

elif page == "6. Export":
    st.header("6. Export Test Artifacts")
    if "requirements_df" not in st.session_state:
        st.session_state.requirements_df = parse_requirements(st.session_state.raw_requirements)
    if "risk_df" not in st.session_state:
        st.session_state.risk_df = analyze_risk(st.session_state.requirements_df)
    if "coverage_df" not in st.session_state:
        st.session_state.coverage_df = generate_coverage_items(
            st.session_state.requirements_df,
            st.session_state.risk_df
        )
    if "test_cases_df" not in st.session_state:
        st.session_state.test_cases_df = generate_test_cases(
            st.session_state.requirements_df,
            st.session_state.risk_df,
            st.session_state.coverage_df
        )

    if st.button("Export CSV / JSON / Excel"):
        paths = export_results(
            st.session_state.requirements_df,
            st.session_state.risk_df,
            st.session_state.coverage_df,
            st.session_state.test_cases_df
        )
        st.success("Export completed.")
        for name, path in paths.items():
            st.write(f"{name}: `{path}`")

elif page == "7. Evidence Checklist":
    st.header("7. Evidence Checklist for Report and Presentation")
    st.write("Take screenshots of the following pages for your final report and PPT:")

    checklist = pd.DataFrame([
        {"Evidence": "Requirement Input page", "Purpose": "Proves FR 1.0 input/parsing"},
        {"Evidence": "Structured Requirements table", "Purpose": "Proves FR 1.1 requirement structuring"},
        {"Evidence": "Risk Analysis table", "Purpose": "Proves FR 2.0 risk scoring and prioritization"},
        {"Evidence": "Coverage Items table", "Purpose": "Proves coverage item identification and strategy selection"},
        {"Evidence": "Test Cases table", "Purpose": "Proves FR 3.0 black-box test generation"},
        {"Evidence": "Editable st.data_editor tables", "Purpose": "Proves human-in-the-loop interactive review"},
        {"Evidence": "Export output files", "Purpose": "Proves FR 6.0 export capability"},
        {"Evidence": "Excel output with multiple sheets", "Purpose": "Proves structured test artifact generation"},
    ])

    st.dataframe(checklist, use_container_width=True)