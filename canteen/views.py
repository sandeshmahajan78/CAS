from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import CreateStaffForm
from .forms import CreateItemForm
from django.contrib.auth.decorators import user_passes_test
from .models import *
from django.contrib.auth.models import User
import uuid
from django.db.models import Sum
from django.http import HttpResponseRedirect, HttpResponse
from django.contrib.auth.hashers import check_password
from reportlab.pdfgen import canvas

# Create your views here.
def index(request):
    return render(request, "index.html")


def loginView(request):
    if request.user.is_authenticated:
        return redirect("home")
    else:
        # User Authentication
        if request.method == "POST":
            username = request.POST.get("username")
            password = request.POST.get("password")

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                return redirect("home")
            else:
                messages.info(request, "Username OR password is incorrect")

        context = {}
        return render(request, "login.html", context)


def logoutUser(request):
    logout(request)
    return redirect("login")


def register(request):
    form = CreateStaffForm()
    if request.method == "POST":
        form = CreateStaffForm(request.POST)
        if form.is_valid():
            form.save()
            user = form.cleaned_data.get("username")
            email = form.cleaned_data.get("email")
            phone = form.cleaned_data.get("phone")
            city = form.cleaned_data.get("city")
            state = form.cleaned_data.get("state")
            pincode = form.cleaned_data.get("pincode")
            Account.objects.create(
                user=User.objects.get(username=user),
                email=email,
                phone=phone,
                city=city,
                state=state,
                pincode=pincode,
                isKStaff="True",
            )
            messages.success(request, user + "was registered as Kitchen Staff")

            return redirect("register")

    context = {"form": form}
    return render(request, "registerStaff.html", context)


def addItems(request):
    if not request.user.is_authenticated:
        return redirect("login")
    form = CreateItemForm()

    if request.method == "POST":
        form = CreateItemForm(request.POST, request.FILES)

        if form.is_valid():
            form.save()
            messages.success(request, "Item added successfully")
            return redirect("addItems")

    context = {"form": form}
    return render(request, "editItems.html", context)


def updateItem(request, itemNo):
    if not request.user.is_authenticated:
        return redirect("login")

    item = Item.objects.get(itemNo=itemNo)
    form = CreateItemForm(instance=item)

    if request.method == "POST":
        form = CreateItemForm(request.POST, request.FILES, instance=item)

        if form.is_valid():
            form.save()
        messages.success(request, "Item modified successfully")
        return redirect("items")

    context = {"form": form}
    return render(request, "editItems.html", context)


def deleteItem(request, itemNo):
    if not request.user.is_authenticated:
        return redirect("login")

    item = get_object_or_404(Item, itemNo=itemNo)
    item.delete()
    messages.success(request, "Item deleted successfully")
    return redirect("items")


def items(request):
    if not request.user.is_authenticated:
        return redirect("login")

    items = Item.objects.all()
    context = {"items": items}
    return render(request, "items.html", context)


def order(request):
    items = Item.objects.all()
    context = {"items": items}

    if request.method == "POST":
        item_ids = request.POST.getlist("item_ids")
        quantities = request.POST.getlist("quantities")

        # ✅ FIX: proper filtering (IMPORTANT)
        filtered = [(i, q) for i, q in zip(item_ids, quantities) if q != '0']

        # ✅ GET CUSTOMER NAME
        customer_name = request.POST.get("customer_name")

        token = int(str(uuid.uuid4().int)[:3])
        while Order.objects.filter(tokenNo=token).exists():
            token = int(str(uuid.uuid4().int)[:3])

        # ✅ CREATE ORDER
        order = Order(tokenNo=token, customer_name=customer_name)
        order.save()

        # ✅ SAVE ITEMS CORRECTLY
        for item_id, quantity in filtered:
            item = Item.objects.get(itemNo=item_id)

            order_item = OrderItem(
                quantity=int(quantity),   # 🔥 IMPORTANT (int)
                item=item
            )
            order_item.save()

            order.items.add(order_item)

        # ✅ TOTAL
        order.totalAmount = order.get_total()
        order.save()

        return HttpResponseRedirect("/billing/{}".format(token))

    return render(request, "order.html", context)
def viewOrders(request):
    if not request.user.is_authenticated:
        return redirect("login")

    orders = Order.objects.all()
    context = {"orders": orders}
    return render(request, "viewOrders.html", context)


def markCompleted(request):
    # Get the list of order ids from the request
    order_ids = request.POST.getlist("order_ids")

    # Iterate over the order ids
    for order_id in order_ids:
        # Get the Order object with the specified id
        order = Order.objects.get(tokenNo=order_id)
        # Get the Account instance that corresponds to the current user
        account = Account.objects.get(user=request.user)
        # Update the isCompleted field of the Order object
        Order.objects.filter(tokenNo=order_id).update(
            isCompleted=True, completedBy=account
        )

    # Redirect to the orders page
    return redirect("viewOrders")


def billing(request, tokenNo):
    if not request.user.is_authenticated:
        return redirect("login")

    orders = Order.objects.filter(tokenNo=tokenNo)

    if request.method == "POST":
        modeOfPayment = request.POST.get("modeOfPayment")
        password = request.POST.get("password")

        if check_password(password, request.user.password):
            order = orders.first()
            order.modeOfPayment = modeOfPayment
            order.isPaid = True
            order.save()

            # Create Bill
            Bill.objects.create(amount=order.totalAmount, order=order)

            # ===== CREATE PDF RESPONSE =====
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename=invoice_{order.tokenNo}.pdf'

            c = canvas.Canvas(response)

            # ===== HEADER =====
            c.setFont("Helvetica-Bold", 20)
            c.drawString(180, 800, "CANTEEN AUTOMATION SYSTEM")

            c.setFont("Helvetica", 14)
            c.drawString(230, 780, "INVOICE")

            # ===== ORDER DETAILS =====
            c.setFont("Helvetica", 12)
            c.drawString(50, 750, f"Order No: {order.tokenNo}")
            c.drawString(50, 730, f"User: {request.user.username}")
            c.drawString(50, 710, f"Date: {order.created_at.strftime('%Y-%m-%d')}")

            # ===== TABLE HEADER =====
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, 670, "Item")
            c.drawString(250, 670, "Qty")
            c.drawString(320, 670, "Price")
            c.drawString(400, 670, "Total")

            c.line(50, 665, 500, 665)

            # ===== TABLE DATA =====
            c.setFont("Helvetica", 11)
            y = 640

            for order_item in order.items.all():
                c.drawString(50, y, order_item.item.name)
                c.drawString(250, y, str(order_item.quantity))
                c.drawString(320, y, str(order_item.item.price))
                c.drawString(400, y, str(order_item.totalAmount))
                y -= 20

            # ===== TOTAL =====
            c.line(50, y, 500, y)
            y -= 20

            c.setFont("Helvetica-Bold", 12)
            c.drawString(300, y, "Total:")
            c.drawString(400, y, f"₹{order.totalAmount}")

            # ===== PAYMENT MODE =====
            y -= 30
            c.setFont("Helvetica", 12)
            c.drawString(50, y, "Payment Mode:")
            c.drawString(200, y, order.get_modeOfPayment_display())

            # ===== FOOTER =====
            y -= 50
            c.setFont("Helvetica-Oblique", 11)
            c.drawString(180, y, "Thank you! Visit Again 🙏")

            # Save PDF
            c.save()

            return response

        else:
            messages.error(request, "Incorrect password")
            return redirect("billing", tokenNo=tokenNo)

    context = {"orders": orders}
    return render(request, "billing.html", context)

def summary(request):

    if not request.user.is_authenticated:
        return redirect("login")

    # Item summary
    items_sorted = OrderItem.objects.select_related('item') \
        .values('item', 'item__name') \
        .annotate(sum=Sum('quantity')) \
        .order_by('-sum')

    # Total revenue
    amount = Order.objects.filter(isPaid=True).aggregate(sum=Sum('totalAmount'))

    # 🔥 ADD THIS (IMPORTANT)
    orders = Order.objects.prefetch_related('items__item').all().order_by('-created_at')

    context = {
        'items': items_sorted,
        'amount': amount,
        'orders': orders   # ✅ THIS FIXES YOUR ISSUE
    }

    return render(request, "summary.html", context)