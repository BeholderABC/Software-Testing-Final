# Test Result Analysis for Target Application

## 1. Target Application

The selected target application is the backend of the Mini E-Commerce System. The testing scope focuses on the Django REST Framework backend, especially the Order Creation API.

Selected module:

* API: `POST /api/orders/create/`
* Backend framework: Django REST Framework
* Test framework: PyTest, pytest-django, DRF APIClient

## 2. Test Execution Summary

The test suite contains 9 automated backend test cases for the Order Creation API.

### Initial Execution Result Before Improvement

* Total test cases: 9
* Passed: 8
* Failed: 1

The failed test case was:

* `test_create_order_with_zero_quantity_should_return_400`

Expected result:

* HTTP 400 Bad Request

Actual result:

* HTTP 201 Created

This means the backend accepted an invalid order item with `quantity = 0`.

## 3. Defect Found

The defect was found through Boundary Value Analysis.

The quantity field should follow this rule:

* Invalid lower boundary: `quantity = 0`
* Valid minimum value: `quantity = 1`
* Valid upper boundary: `quantity = available stock`
* Invalid upper boundary: `quantity = stock + 1`

The system correctly rejected insufficient stock, but it did not explicitly validate whether the quantity was greater than 0. As a result, an order item with zero quantity could still be created.

## 4. Improvement Made

To fix the defect, validation logic was added to the Order Creation API. The backend now checks whether each order item contains a valid positive integer quantity before checking stock and creating the order item.

Added validation rule:

```python
if quantity <= 0:
    order.delete()
    return Response(
        {"error": "Quantity must be greater than 0"},
        status=status.HTTP_400_BAD_REQUEST
    )
```

## 5. Re-test Result

After applying the improvement, the PyTest suite was executed again.

Final execution result:

* Total test cases: 9
* Passed: 9
* Failed: 0

This confirms that the defect was fixed successfully.

## 6. Analysis

The result shows that the generated boundary value test case was useful in identifying an input validation weakness in the target application. Although the API handled normal orders, missing customer information, non-existing products, and insufficient stock correctly, it missed the zero-quantity boundary case.

This demonstrates that systematic test design is useful because it can reveal defects that may not be found by only testing common valid inputs. The improvement also shows the value of interactive review, where the tester reviews generated test cases, executes them, identifies missing validation, and improves the target application based on evidence.
