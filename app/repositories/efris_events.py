from __future__ import annotations

from decimal import Decimal

from app.oracle import OracleDatabase


class OracleEfrisEventRepository:
    def __init__(self, db: OracleDatabase):
        self.db = db

    def list_devices(self, tin: str):
        sql = """
        SELECT DEVICE_NO, TAXPAYER_ID, DEVICE_SEQ, DEVICE_TYPE
        FROM EFRIS_DEVICE
        WHERE TAXPAYER_ID = :tin
        ORDER BY DEVICE_SEQ, DEVICE_NO
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tin=tin)
                return [
                    {
                        "device_no": row[0],
                        "taxpayer_id": row[1],
                        "device_seq": int(row[2]),
                        "device_type": row[3],
                    }
                    for row in cur.fetchall()
                ]

    def taxpayer_exists(self, tin: str) -> bool:
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM TAXPAYER WHERE TAXPAYER_ID = :tin", tin=tin)
                return cur.fetchone() is not None

    def create_event(
        self,
        source_id: str,
        tin: str,
        device_no: str,
        seller_reference_no: str | None,
        return_code: str,
        return_msg: str,
        gross_amount: Decimal,
        tax_amount: Decimal,
        currency: str,
        item_description: str | None,
        create_user_id: str = "WEB_APP",
    ):
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                if not seller_reference_no:
                    cur.execute("SELECT SEQ_EFRIS_SELLER_REF.NEXTVAL FROM DUAL")
                    sequence_value = int(cur.fetchone()[0])
                    seller_reference_no = f"{tin}-INV-{sequence_value:08d}"

                cur.execute(
                    """
                    INSERT INTO T_INVOICE_ERROR_LOG
                        (ID, TIN, DEVICE_NO, SELLER_REFERENCE_NO, RETURN_CODE, RETURN_MSG,
                         GROSS_AMOUNT, TAX_AMOUNT, CURRENCY, ITEM_DESCRIPTION,
                         CREATE_USER_ID, CREATE_DATE)
                    VALUES
                        (:source_id, :tin, :device_no, :seller_reference_no, :return_code,
                         :return_msg, :gross_amount, :tax_amount, :currency,
                         :item_description, :create_user_id, SYSDATE)
                    """,
                    source_id=source_id,
                    tin=tin,
                    device_no=device_no,
                    seller_reference_no=seller_reference_no,
                    return_code=return_code,
                    return_msg=return_msg,
                    gross_amount=gross_amount,
                    tax_amount=tax_amount,
                    currency=currency,
                    item_description=item_description,
                    create_user_id=create_user_id,
                )
            conn.commit()

        return self.get_created_event(source_id, tin, seller_reference_no)

    def get_created_event(self, source_id: str, tin: str, seller_reference_no: str):
        sql = """
        SELECT
            ERROR_EVENT_ID,
            ID,
            TIN,
            DEVICE_NO,
            SELLER_REFERENCE_NO,
            RETURN_CODE,
            RETURN_MSG,
            GROSS_AMOUNT,
            TAX_AMOUNT,
            CURRENCY,
            ITEM_DESCRIPTION,
            CREATE_USER_ID,
            CREATE_DATE
        FROM T_INVOICE_ERROR_LOG
        WHERE ID = :source_id
          AND TIN = :tin
          AND SELLER_REFERENCE_NO = :seller_reference_no
        ORDER BY ERROR_EVENT_ID DESC
        FETCH FIRST 1 ROW ONLY
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    source_id=source_id,
                    tin=tin,
                    seller_reference_no=seller_reference_no,
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "error_event_id": int(row[0]),
            "id": row[1],
            "tin": row[2],
            "device_no": row[3],
            "seller_reference_no": row[4],
            "return_code": row[5],
            "return_msg": row[6],
            "gross_amount": row[7],
            "tax_amount": row[8],
            "currency": row[9],
            "item_description": row[10],
            "create_user_id": row[11],
            "create_date": row[12],
        }
