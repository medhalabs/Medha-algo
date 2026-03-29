from fastapi import APIRouter, Depends

from app.dhan_api.data.schemas.quotes import ExpiryListBody, OptionChainBody
from app.deps import get_dhan
from dhanhq import dhanhq

router = APIRouter()


@router.post("/option-chain", summary="Option chain")
def option_chain(body: OptionChainBody, d: dhanhq = Depends(get_dhan)):
    return d.option_chain(
        body.under_security_id,
        body.under_exchange_segment,
        body.expiry,
    )


@router.post("/option-chain/expiry-list", summary="Expiry list for underlying")
def expiry_list(body: ExpiryListBody, d: dhanhq = Depends(get_dhan)):
    return d.expiry_list(
        body.under_security_id,
        body.under_exchange_segment,
    )
