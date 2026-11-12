"""ATO and ABR pages cited by the report. Thresholds themselves live in config/rules.toml."""

SALES = "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/completing-your-bas-for-gst/complete-your-bas/step-1-sales"
PURCHASES = "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/completing-your-bas-for-gst/complete-your-bas/step-3-purchases"
SUMMARY = "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/completing-your-bas-for-gst/complete-your-bas/step-5-summary"
METHODS = "https://www.ato.gov.au/businesses-and-organisations/preparing-lodging-and-paying/business-activity-statements-bas/goods-and-services-tax-gst/gst-reporting-methods"
TAX_INVOICE = "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/tax-invoices"
GST_CREDIT = "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/claiming-gst-credits/when-you-can-claim-a-gst-credit"
CANNOT_CLAIM = "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/claiming-gst-credits/when-you-cannot-claim-a-gst-credit"
GST_FREE = "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/when-to-charge-gst-and-when-not-to/gst-free-sales/"
GST_FREE_FOOD = "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/when-to-charge-gst-and-when-not-to/gst-free-sales/gst-free-food"
ACCOUNTING_METHOD = "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/accounting-for-gst-in-your-business/choosing-an-accounting-method"
ABR_REGISTER = "https://abr.business.gov.au/Documentation/WebServiceRegistration"

SOURCE_TITLES = {
    SALES: "ATO: G1 total sales",
    PURCHASES: "ATO: G10 capital purchases and G11 non-capital purchases",
    SUMMARY: "ATO: 1A GST on sales and 1B GST on purchases",
    METHODS: "ATO: GST reporting methods (Simpler BAS and full reporting)",
    TAX_INVOICE: "ATO: tax invoices",
    GST_CREDIT: "ATO: when you can claim a GST credit",
    CANNOT_CLAIM: "ATO: when you cannot claim a GST credit",
    GST_FREE: "ATO: GST-free sales",
    GST_FREE_FOOD: "ATO: GST-free food",
    ACCOUNTING_METHOD: "ATO: cash and non-cash accounting for GST",
    ABR_REGISTER: "ABR: register for a free ABN Lookup GUID",
}
