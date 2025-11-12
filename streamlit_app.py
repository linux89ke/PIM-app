flag_reason_comment_mapping = {
    "Sensitive Brand Issues": ("1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)", "Please contact vendor support for sale of..."),
    "Seller Approve to sell books": ("1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim", """Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing.
This step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."""),
    "Perfume Price Check": ("1000029 - Perfume Price Deviation >= $30", "Price is $30+ below reference. Contact Seller Support with claim #{{CLAIM_ID}} for authenticity verification."),
    "Seller Approved to Sell Perfume": ("1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim", """Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing.
This step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."""),
    "Single-word NAME": ("1000008 - Kindly Improve Product Name Description", """Kindly update the product title using this format: Name – Type of the Products – Color.
If available, please also add key details such as weight, capacity, type, and warranty to make the title clear and complete for customers."""),
    "Missing BRAND or NAME": ("1000001 - Brand NOT Allowed", "Brand NOT Allowed"),
    "Generic BRAND Issues": ("1000001 - Brand NOT Allowed", "Please use Fashion as brand for Fashion items- Kindly request for the creation of this product's actual brand name by filling this form: https://bit.ly/2kpjja8"),
    "Missing COLOR": ("1000005 - Kindly confirm the actual product colour", "Kindly add color on the color field"),
    "BRAND name repeated in NAME": ("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", """Please do not write the brand name in the Product Name field. The brand name should only be written in the Brand field.
If you include it in both fields, it will show up twice in the product title on the website"""),
    "Duplicate product": ("1000007 - Other Reason", "kindly note product was rejected because its a duplicate product"),
    
    # ← NEW: Updated Counterfeit Sneakers
    "Counterfeit Sneakers": (
        "1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)",
        """Your listing has been rejected as Jumia’s technical team has confirmed the product is counterfeit.
As a result, this item cannot be sold on the platform.

Please ensure that all products listed are 100% authentic to comply with Jumia’s policies and protect customer trust.

If you believe this decision is incorrect or need further clarification, please contact the Seller Support team"""
    ),
}
