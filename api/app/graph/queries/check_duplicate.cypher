MATCH (v:Vendor {gstin: $gstin})-[:ISSUED]->(i:Invoice {number_norm: $number_norm, fy: $fy})
RETURN count(i) > 0 AS is_duplicate, i.id AS existing_id
