# Confidence routing thresholds
# Invoices with 0.80 <= conf < 0.90 use Flash but are not flagged high-risk (intentional middle band).
ROUTING_CONF_THRESHOLD = 0.90   # Flash vs Pro routing decision
HIGH_RISK_CONF_THRESHOLD = 0.80 # Below this: invoice flagged high-risk in Excel output
