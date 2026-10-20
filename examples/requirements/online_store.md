# Online store: checkout and order tracking

## Functional requirements

A customer can add one or more products to a shopping cart and change item quantities before checkout.

When the customer confirms an order, the system must validate stock availability and calculate the final price including delivery and applicable taxes. If any item is unavailable, the system must not charge the customer and must explain which item is unavailable.

After successful payment, the system creates an order and sends an order confirmation email. Customers can view the current status of their own orders.

Support agents can search orders by order number and help customers with delivery problems. Support agents must not be able to view full payment card details.

## Non-functional requirements

During normal operation, checkout should support 120 requests per second. During a seasonal sale, traffic may reach 400 requests per second.

The checkout API should respond within 300 ms at the 95th percentile under normal load.

The service should be available at least 99.9% of each calendar month.

Customer and order data must be encrypted in transit and at rest.

## Open questions and conflicting statements

The product team says an order confirmation email must be sent within 10 seconds. An older operations note says confirmation emails may be delayed by up to 2 minutes during peak traffic. The required peak-load email delivery target needs confirmation.

The business brief says order history should be retained for 2 years. The compliance note says financial order records must be retained for 7 years. Clarify whether these statements refer to different data categories or conflict.

The document does not specify a maximum cart size, the payment provider, or the recovery objective after a regional outage.
