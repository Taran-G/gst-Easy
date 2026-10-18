MATCH (v:Vendor {gstin: $gstin})-[:SUPPLIES]->(it:Item)-[:USED_IN]->(co:CustomerOrder)
OPTIONAL MATCH (v)-[:ISSUED]->(i:Invoice)
RETURN v.gstin AS vendor_gstin, coalesce(v.legal_name, v.trade_name, v.gstin) AS vendor_name,
       it.name AS item_name, co.number AS order_number, co.customer AS customer,
       co.due_date AS due_date, co.value AS order_value,
       collect(DISTINCT i.id) AS invoices,
       sum(i.cgst + i.sgst + i.igst) AS itc_exposed

