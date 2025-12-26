from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.schemas import Review as ReviewSchema, ReviewCreate
from app.models import Review as ReviewModel, Product as ProductModel, User as UserModel
from app.db_depends import get_async_db
from app.routers.products import router as products_router
from app.auth import get_current_buyer, get_current_admin
from app.services import update_product_rating


router = APIRouter(
    prefix="/reviews",
    tags=["reviews"]
)

@router.get("/", response_model=list[ReviewSchema])
async def get_all_reviews(db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает список всех активных отзывов.
    """
    result = await db.scalars(select(ReviewModel).where(ReviewModel.is_active == True))
    return result.all()

@products_router.get("/{product_id}/reviews", response_model=list[ReviewSchema])
async def get_reviews_by_product(product_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    Возвращает список активных отзывов для указанного товара.
    """
    product_result = await db.scalars(select(ProductModel).where(ProductModel.id == product_id,
                                                   ProductModel.is_active == True))
    product = product_result.first()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не существует или неактивен")

    reviews_result = await db.scalars(select(ReviewModel).where(ReviewModel.product_id == product_id,
                                                                ReviewModel.is_active == True))

    return reviews_result.all()

@router.post("/", response_model=ReviewSchema, status_code=201)
async def create_review(
        review: ReviewCreate,
        db: AsyncSession = Depends(get_async_db),
        current_user: UserModel = Depends(get_current_buyer)
):
    """
    Создаёт новый отзыв, привязанный к текущему покупателю (только для 'buyer').
    """
    product = await db.scalar(select(ProductModel).where(ProductModel.id == review.product_id,
                                                         ProductModel.is_active == True))
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не существует или неактивен")

    user = await db.scalar(select(ReviewModel).where(ReviewModel.product_id == review.product_id,
                                                     ReviewModel.user_id == current_user.id))
    if user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Вы уже оставили отзыв на этот товар")

    db_review = ReviewModel(**review.model_dump(), user_id=current_user.id)
    db.add(db_review)

    await update_product_rating(db, product.id)
    await db.refresh(db_review)

    return db_review

@router.delete("/{review_id}")
async def delete_review(review_id: int,
                        current_user: UserModel = Depends(get_current_admin),
                        db: AsyncSession = Depends(get_async_db)) -> dict:
    """
    Выполняет мягкое удаление отзыва по её ID, устанавливая is_active = False. (только для 'admin')
    """
    review = await db.scalar(
        select(ReviewModel).where(
            ReviewModel.id == review_id,
            ReviewModel.is_active == True
        )
    )
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отзыв не существует или неактивен")

    review.is_active = False
    await update_product_rating(db, review.product_id)
    await db.commit()

    return {"message": "Review deleted"}
