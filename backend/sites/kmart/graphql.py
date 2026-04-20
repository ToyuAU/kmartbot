"""
All Kmart GraphQL mutations and query payloads.
Ported and cleaned from kmartbot-main/Classes/post_data.py and Bot.py.

Payload builders return plain dicts — serialised to JSON by the caller.
GraphQL queries are kept as-is from the original (they must match exactly).
"""

import random
import string
from typing import Optional

from backend.models.profile import Profile

KMART_GRAPHQL = "https://api.kmart.com.au/gateway/graphql"

# Known per-SKU max orderable quantities.
# Falls back to 1 for unknown SKUs.
SKU_QUANTITY_MAP: dict[str, int] = {
    "43556700": 5,  "43350070": 5,  "43350254": 5,  "43350230": 5,
    "43350223": 5,  "43405879": 5,  "43675661": 10, "43556670": 5,
    "43648146": 10, "43718443": 5,  "43718450": 5,  "43718436": 5,
    "43675449": 5,  "43726806": 5,  "43580668": 10, "43252695": 10,
    "43718702": 5,  "43718696": 5,  "43724338": 5,  "43737024": 5,
    "43601233": 5,  "43718740": 5,  "43744992": 5,  "43756063": 3,
    "43756032": 10,
}

# Shared GraphQL fragments
_BASIC_BAG_FIELDS = """
fragment BasicBagFields on Cart {
  id version
  postcodeSelector { postalCode state city country __typename }
  totalPrice { centAmount __typename }
  __typename
}"""

_LINE_ITEM_FIELDS = """
fragment LineItemFields on LineItem {
  id name(locale: "en") quantity
  price { value { centAmount __typename } __typename }
  totalPrice { centAmount __typename }
  variant {
    id sku image(input: {preset: thumbnail}) imageKey
    attributes { name value __typename }
    __typename
  }
  custom { fields { offerId __typename } __typename }
  __typename
}"""

_BAG_FIELDS = """
fragment BagFields on Cart {
  id version country customerId catchMembership onepassFreeShipping
  fulfillmentMethod flyBuysNumber expressOrder teamMemberDiscountCardNumber
  selectedCncStoreId reviewConsent kmailSignup onepassUUID selectedCncStoreId expressOrder
  postcodeSelector { postalCode state city country __typename }
  totalPrice { centAmount __typename }
  totalDiscount { discountAmount { centAmount __typename } discountType __typename }
  shippingInfo { shippingMethodName shippingRate { price { centAmount __typename } __typename } __typename }
  shippingAddress {
    firstName lastName email phone streetName city state country postalCode
    company deliveryInstructions isAuthorisedToLeave additionalAddressInfo region __typename
  }
  billingAddress {
    firstName lastName email phone streetName city state country postalCode
    company additionalAddressInfo region __typename
  }
  itemShippingAddresses { key streetName city state country postalCode __typename }
  __typename
}"""


def _gen_email(config: dict) -> str:
    """Generate a random order email."""
    if config.get("use_gmail_spoofing") and config.get("gmail_spoofing_email"):
        base = config["gmail_spoofing_email"]
        username, domain = base.split("@", 1)
        rand = "".join(random.choices(string.ascii_lowercase, k=5)) + \
               "".join(random.choices(string.digits, k=4))
        return f"{username}+{rand}@{domain}"
    elif config.get("catchall_domain"):
        fn = "".join(random.choices(string.ascii_lowercase, k=5))
        ln = "".join(random.choices(string.ascii_lowercase, k=5))
        return f"{fn}{ln}{random.randint(100, 999)}@{config['catchall_domain']}"
    else:
        return f"user{random.randint(10000, 99999)}@example.com"


# ── Payload builders ──────────────────────────────────────────────────────────

def create_cart(city: str = "Glen Waverley", postcode: str = "3150") -> dict:
    return {
        "operationName": "createMyBag",
        "variables": {
            "draft": {
                "currency": "AUD",
                "country": "AU",
                "shippingAddress": {"country": "AU"},
                "postcodeSelector": (
                    f'{{"city":"{city}","postalCode":"{postcode}",'
                    f'"state":"VIC","country":"AU"}}'
                ),
                "selectedCncStoreId": "1001",
            }
        },
        "query": (
            "mutation createMyBag($draft: MyCartDraft!) {\n"
            "  createMyCart(draft: $draft) {\n"
            "    id version\n"
            "    postcodeSelector { postalCode __typename }\n"
            "    __typename\n"
            "  }\n"
            "}\n"
        ),
    }


def add_to_cart(cart_id: str, sku: str, quantity: Optional[int] = None) -> dict:
    qty = quantity or SKU_QUANTITY_MAP.get(sku, 1)
    return {
        "operationName": "updateMyBag",
        "variables": {
            "id": cart_id,
            "version": 415,
            "actions": [
                {"addLineItem": {"sku": sku, "quantity": int(qty)}},
                {"setCustomField": {"name": "selectedCncStoreId", "value": "1226"}},
            ],
        },
        "query": (
            "mutation updateMyBag($id: String!, $version: Long!, $actions: [MyCartUpdateAction!]!) {\n"
            "  updateMyCart(id: $id, version: $version, actions: $actions) {\n"
            "    ...BasicBagFields\n"
            "    lineItems { ...LineItemFields __typename }\n"
            "    __typename\n"
            "  }\n"
            "}\n"
        ) + _BASIC_BAG_FIELDS + _LINE_ITEM_FIELDS,
    }


def set_shipping(cart_id: str, profile: Profile, config: dict) -> tuple[str, dict]:
    """
    Returns (email_used, payload).
    email is generated here so the caller can log/track it.
    """
    email = _gen_email(config)
    addr = {
        "firstName": profile.first_name,
        "lastName": profile.last_name,
        "email": email,
        "phone": profile.mobile,
        "streetName": profile.address1,
        "city": profile.city,
        "state": profile.state,
        "country": "AU",
        "postalCode": profile.postcode,
        "company": "",
        "deliveryInstructions": "",
        "isAuthorisedToLeave": True,
        "additionalAddressInfo": None,
        "region": None,
    }
    billing_addr = {k: v for k, v in addr.items()
                    if k not in ("deliveryInstructions", "isAuthorisedToLeave")}

    payload = {
        "operationName": "updateMyBagWithoutBagStockAvailability",
        "variables": {
            "id": cart_id,
            "version": 26,
            "actions": [
                {"setShippingAddress": {"address": addr}},
                {"setBillingAddress": {"address": billing_addr}},
                {"addItemShippingAddress": {
                    "address": {
                        "key": "storeAddress",
                        "streetName": "C&C \u2013 No Address Specified",
                        "city": profile.city,
                        "state": profile.state,
                        "postalCode": profile.postcode,
                        "country": "AU",
                    }
                }},
                {"setCustomField": {"name": "reviewConsent", "value": "false"}},
                {"setCustomField": {"name": "kmailSignup", "value": "false"}},
            ],
        },
        "query": (
            "mutation updateMyBagWithoutBagStockAvailability"
            "($id: String!, $version: Long!, $actions: [MyCartUpdateAction!]!) {\n"
            "  updateMyCart(id: $id, version: $version, actions: $actions) {\n"
            "    ...BagFields\n"
            "    lineItems { ...LineItemFields __typename }\n"
            "    __typename\n"
            "  }\n"
            "}\n"
        ) + _BAG_FIELDS + _LINE_ITEM_FIELDS,
    }
    return email, payload


def apply_staff_code(staff_code: str) -> dict:
    return {
        "operationName": "ApplyTeamMemberDiscount",
        "variables": {"input": {"teamMemberCardNumber": staff_code}},
        "query": (
            "mutation ApplyTeamMemberDiscount($input: TeamMemberDiscountCardInput!) {\n"
            "  applyTeamMemberDiscount(input: $input) {\n"
            "    id\n"
            "    totalDiscount { discountAmount { centAmount __typename } __typename }\n"
            "    __typename\n"
            "  }\n"
            "}\n"
        ),
    }


def apply_flybuys(cart_id: str, version: int, flybuys_number: str) -> dict:
    return {
        "operationName": "updateMyBagWithoutBagStockAvailability",
        "variables": {
            "id": cart_id,
            "version": version,
            "actions": [{"setCustomField": {"value": flybuys_number, "name": "flyBuysNumber"}}],
        },
        "query": (
            "mutation updateMyBagWithoutBagStockAvailability"
            "($id: String!, $version: Long!, $actions: [MyCartUpdateAction!]!) {\n"
            "  updateMyCart(id: $id, version: $version, actions: $actions) {\n"
            "    ...BagFields\n"
            "    lineItems { ...LineItemFields __typename }\n"
            "    __typename\n"
            "  }\n"
            "}\n"
        ) + _BAG_FIELDS + _LINE_ITEM_FIELDS,
    }


def create_3ds_token(one_time_token: str) -> dict:
    return {
        "operationName": "create3DSToken",
        "variables": {
            "oneTimeToken": one_time_token,
            "gatewayType": "MasterCard",
            "useSavedCard": False,
            "saveCardOption": False,
        },
        "query": (
            "mutation create3DSToken($oneTimeToken: String!, $gatewayType: String, "
            "$useSavedCard: Boolean, $saveCardOption: Boolean) {\n"
            "  create3DSToken(\n"
            "    oneTimeToken: $oneTimeToken\n"
            "    gatewayType: $gatewayType\n"
            "    useSavedCard: $useSavedCard\n"
            "    saveCardOption: $saveCardOption\n"
            "  )\n"
            "}\n"
        ),
    }


def charge_paydock(charge_3ds_id: str) -> dict:
    return {
        "operationName": "chargePayDockWithToken",
        "variables": {
            "type": "TOKEN_3DS",
            "token": charge_3ds_id,
            "gatewayType": "MasterCard",
            "saveCard": False,
            "isCreateAccount": False,
        },
        "query": (
            "mutation chargePayDockWithToken($type: TokenType!, $token: String!, "
            "$gatewayType: String!, $saveCard: Boolean, $isCreateAccount: Boolean) {\n"
            "  chargePayDockWithToken(\n"
            "    type: $type\n"
            "    token: $token\n"
            "    gatewayType: $gatewayType\n"
            "    saveCard: $saveCard\n"
            "    isCreateAccount: $isCreateAccount\n"
            "  ) {\n"
            "    paydockChargeId paymentId orderNumber accountCreationStatus __typename\n"
            "  }\n"
            "}\n"
        ),
    }


def refresh_bag() -> dict:
    """Used by the SKU monitor and Flybuys version fetch."""
    return {
        "operationName": "refreshMyBag",
        "variables": {},
        "query": (
            "mutation refreshMyBag {\n"
            "  refreshMyCart {\n"
            "    ...BagFields\n"
            "    lineItems { ...LineItemFields __typename }\n"
            "    __typename\n"
            "  }\n"
            "}\n"
        ) + _BAG_FIELDS + _LINE_ITEM_FIELDS,
    }


# Shipping availability fragment — returned by refreshMyCart when requested.
# Used by the WATCHING_STOCK step to tell cartable-but-not-shippable from shippable.
_BAG_STOCK_AVAILABILITY_FIELDS = """
fragment BagStockAvailabilityFields on Cart {
  bagStockAvailability {
    BUCKET_INFO {
      HOME_DELIVERY {
        bucketType
        logisticOrders {
          earliestDeliveryDate
          items { offerId sku __typename }
          latestDeliveryDate sellerName shippingFee __typename
        }
        __typename
      }
      EXPRESS_DELIVERY {
        bucketType
        logisticOrders {
          earliestDeliveryDate
          items { offerId sku __typename }
          latestDeliveryDate sellerName shippingFee __typename
        }
        __typename
      }
      CLICK_AND_COLLECT {
        bucketType
        logisticOrders {
          earliestDeliveryDate
          items { offerId sku __typename }
          latestDeliveryDate sellerName shippingFee __typename
        }
        __typename
      }
      __typename
    }
    HOME_DELIVERY { keyCode poolName stock __typename }
    __typename
  }
  __typename
}"""


def refresh_bag_with_availability() -> dict:
    """
    refreshMyCart with bagStockAvailability — the real shipping signal.
    Poll this while watching for stock; `bucketType != "OOS"` means shippable.
    """
    return {
        "operationName": "refreshMyBag",
        "variables": {},
        "query": (
            "mutation refreshMyBag {\n"
            "  refreshMyCart {\n"
            "    ...BagFields\n"
            "    ...BagStockAvailabilityFields\n"
            "    lineItems { ...LineItemFields __typename }\n"
            "    __typename\n"
            "  }\n"
            "}\n"
        ) + _BAG_FIELDS + _BAG_STOCK_AVAILABILITY_FIELDS + _LINE_ITEM_FIELDS,
    }
